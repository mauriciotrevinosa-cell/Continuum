"""Enqueue, claim and guarded status transitions (ADR-0002).

PostgreSQL is the sole durable job store (D-02). Claiming uses
``FOR UPDATE SKIP LOCKED``, which is why SQLite was rejected as a Phase 0
substrate: it has no such construct, so the queue would have been built on a
different concurrency model than the one it ships with, and acceptance tests
110.6-110.11 would have been testing the wrong thing (OQ-1).
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from continuum_core import StructuredError, content_hash_bytes, uuid7
from continuum_db.enums import BlockedReason, JobEventType, JobStatus
from continuum_db.models import Job, JobDependency, JobEvent
from continuum_observability import current_correlation_id, get_logger
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from continuum_jobs.states import assert_transition, is_terminal, next_backoff_seconds

__all__ = [
    "block_job",
    "claim_next_job",
    "compute_dedupe_key",
    "enqueue",
    "fail_job",
    "record_event",
    "request_cancel",
    "request_pause",
    "resume_job",
    "retry_job",
    "transition",
    "unblock_ready_dependents",
]

log = get_logger("continuum.jobs.queue")


def compute_dedupe_key(job_type: str, payload: dict[str, Any], recipe_version: str | None) -> str:
    """Stable key for "the same work" (F-26).

    Enqueue becomes get-or-create, so double-clicking a button yields one job
    rather than a race between two identical workers.
    """
    import json

    canonical = json.dumps(
        {"t": job_type, "p": payload, "r": recipe_version}, sort_keys=True, separators=(",", ":")
    )
    return content_hash_bytes(canonical.encode())[:64]


def record_event(
    session: Session,
    job_id: uuid.UUID,
    event_type: JobEventType,
    *,
    from_status: JobStatus | None = None,
    to_status: JobStatus | None = None,
    detail: dict[str, Any] | None = None,
    worker_id: uuid.UUID | None = None,
) -> JobEvent:
    """Append to the immutable audit trail (ADR-0002 section 11)."""
    event = JobEvent(
        job_id=job_id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        detail=detail,
        worker_id=worker_id,
        correlation_id=current_correlation_id(),
    )
    session.add(event)
    return event


def enqueue(
    session: Session,
    job_type: str,
    *,
    payload: dict[str, Any] | None = None,
    priority: int = 0,
    resource_class: str = "cpu",
    max_attempts: int = 5,
    units_total: int | None = None,
    recipe_version: str | None = None,
    dedupe: bool = True,
    depends_on: list[uuid.UUID] | None = None,
) -> tuple[Job, bool]:
    """Create a job, or return the existing equivalent one.

    Returns ``(job, created)``. Deduplication is enforced by a partial unique
    index over non-terminal statuses, so it holds even against a concurrent
    enqueue from another process -- an application-level check alone would
    still race.
    """
    body = payload or {}
    key = compute_dedupe_key(job_type, body, recipe_version) if dedupe else None

    if key is not None:
        existing = session.execute(
            select(Job).where(Job.dedupe_key == key, Job.status.not_in(_terminal_values()))
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False

    job = Job(
        id=uuid7(),
        job_type=job_type,
        status=JobStatus.QUEUED,
        payload=body,
        priority=priority,
        resource_class=resource_class,
        max_attempts=max_attempts,
        units_total=units_total,
        recipe_version=recipe_version,
        dedupe_key=key,
        correlation_id=current_correlation_id(),
    )
    session.add(job)

    try:
        session.flush()
    except IntegrityError:
        # Lost the race against a concurrent enqueue; adopt the winner.
        session.rollback()
        if key is None:
            raise
        winner = session.execute(
            select(Job).where(Job.dedupe_key == key, Job.status.not_in(_terminal_values()))
        ).scalar_one_or_none()
        if winner is None:
            raise
        return winner, False

    record_event(session, job.id, JobEventType.CREATED, to_status=JobStatus.QUEUED)

    for parent_id in depends_on or []:
        session.add(JobDependency(job_id=job.id, depends_on_job_id=parent_id))
    if depends_on:
        _apply_status(
            session,
            job,
            JobStatus.BLOCKED,
            blocked_reason=BlockedReason.DEPENDENCY,
            remediation={
                "message": "Waiting on prerequisite jobs.",
                "depends_on": [str(p) for p in depends_on],
            },
        )
    session.flush()
    return job, True


def _terminal_values() -> list[JobStatus]:
    return [JobStatus.SUCCEEDED, JobStatus.FAILED_FINAL, JobStatus.CANCELLED]


def transition(
    session: Session,
    job: Job,
    target: JobStatus,
    *,
    worker_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    blocked_reason: BlockedReason | None = None,
    remediation: dict[str, Any] | None = None,
) -> Job:
    """Move a job to ``target``, refusing any transition not in the table."""
    assert_transition(job.status, target, job_id=job.id)
    previous = job.status
    _apply_status(session, job, target, blocked_reason=blocked_reason, remediation=remediation)
    record_event(
        session,
        job.id,
        JobEventType.TRANSITION,
        from_status=previous,
        to_status=target,
        detail=detail,
        worker_id=worker_id,
    )
    log.info(
        "job transition",
        extra={"job_id": str(job.id), "from": previous.value, "to": target.value},
    )
    return job


def _apply_status(
    session: Session,
    job: Job,
    target: JobStatus,
    *,
    blocked_reason: BlockedReason | None = None,
    remediation: dict[str, Any] | None = None,
) -> None:
    job.status = target
    # The CHECK constraint requires reason IFF blocked, so keep them in step.
    job.blocked_reason = blocked_reason if target is JobStatus.BLOCKED else None
    if target is JobStatus.BLOCKED:
        job.remediation = remediation
    if target is JobStatus.RUNNING and job.started_at is None:
        job.started_at = dt.datetime.now(dt.UTC)
    if is_terminal(target):
        job.completed_at = dt.datetime.now(dt.UTC)
        job.lease_owner = None
        job.lease_expires_at = None
    session.flush()


def claim_next_job(
    session: Session,
    *,
    worker_id: uuid.UUID,
    resource_classes: list[str],
    lease_seconds: int,
    concurrency_limits: dict[str, int] | None = None,
) -> Job | None:
    """Atomically claim one runnable job, or return ``None``.

    ``FOR UPDATE SKIP LOCKED`` lets several workers poll the same table
    without blocking each other or handing the same job to two workers.
    """
    eligible = list(resource_classes)
    if concurrency_limits:
        eligible = [
            rc
            for rc in eligible
            if _running_count(session, rc) < concurrency_limits.get(rc, 1_000_000)
        ]
    if not eligible:
        return None

    row = session.execute(
        select(Job)
        .where(
            Job.status.in_((JobStatus.QUEUED, JobStatus.FAILED_RETRYABLE)),
            Job.run_after <= func.now(),
            Job.resource_class.in_(eligible),
        )
        .order_by(Job.priority.desc(), Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).scalar_one_or_none()

    if row is None:
        return None

    if row.status is JobStatus.FAILED_RETRYABLE:
        transition(session, row, JobStatus.QUEUED, detail={"reason": "retry due"})
    transition(session, row, JobStatus.RUNNING, worker_id=worker_id)
    row.lease_owner = worker_id
    row.lease_expires_at = _lease_deadline(session, lease_seconds)
    record_event(
        session,
        row.id,
        JobEventType.LEASE_ACQUIRED,
        worker_id=worker_id,
        detail={"lease_seconds": lease_seconds},
    )
    session.flush()
    return row


def _running_count(session: Session, resource_class: str) -> int:
    return int(
        session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.status == JobStatus.RUNNING, Job.resource_class == resource_class)
        ).scalar_one()
    )


def _lease_deadline(session: Session, lease_seconds: int) -> dt.datetime:
    """Compute expiry from the DATABASE clock, never the worker's (D-09).

    Clock skew between two machines must not be able to expire a live lease
    and cause the same units to run twice.
    """
    return session.execute(
        select(func.now() + func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds))
    ).scalar_one()


def request_pause(session: Session, job: Job) -> Job:
    """Set the pause FLAG. Never writes status directly (F-28)."""
    job.pause_requested = True
    record_event(session, job.id, JobEventType.PAUSE_REQUESTED)
    if job.status is JobStatus.QUEUED:
        transition(session, job, JobStatus.PAUSED)
    elif job.status is JobStatus.RUNNING:
        transition(session, job, JobStatus.PAUSING)
    session.flush()
    return job


def request_cancel(session: Session, job: Job) -> Job:
    """Set the cancel FLAG. Never writes status directly (F-28)."""
    job.cancel_requested = True
    record_event(session, job.id, JobEventType.CANCEL_REQUESTED)
    if job.status in (JobStatus.QUEUED, JobStatus.PAUSED, JobStatus.BLOCKED):
        transition(session, job, JobStatus.CANCELLED)
    elif job.status in (JobStatus.RUNNING, JobStatus.PAUSING):
        transition(session, job, JobStatus.CANCELLING)
    session.flush()
    return job


def resume_job(session: Session, job: Job) -> Job:
    """Clear the pause flag and return a paused job to the queue."""
    job.pause_requested = False
    if job.status is JobStatus.PAUSED:
        transition(session, job, JobStatus.QUEUED)
    session.flush()
    return job


def retry_job(session: Session, job: Job) -> Job:
    """Return a retryable failure to the queue immediately."""
    if job.status is not JobStatus.FAILED_RETRYABLE:
        assert_transition(job.status, JobStatus.QUEUED, job_id=job.id)
    job.run_after = _database_now(session)
    transition(session, job, JobStatus.QUEUED, detail={"reason": "manual retry"})
    session.flush()
    return job


def fail_job(
    session: Session, job: Job, error: StructuredError, *, worker_id: uuid.UUID | None = None
) -> Job:
    """Record a structured failure and decide retryable vs final (F-25, F-70)."""
    payload = error.to_dict()
    job.last_error = payload
    history = list(job.error_history or [])
    history.append({**payload, "attempt": job.attempt})
    job.error_history = history[-20:]  # capped: diagnosis needs recent, not all

    exhausted = job.attempt + 1 >= job.max_attempts
    if error.retryable and not exhausted:
        job.attempt += 1
        delay = next_backoff_seconds(job.attempt)
        job.run_after = _database_now(session) + dt.timedelta(seconds=delay)
        transition(
            session,
            job,
            JobStatus.FAILED_RETRYABLE,
            worker_id=worker_id,
            detail={"error": payload, "retry_in_seconds": round(delay, 2)},
        )
    else:
        job.attempt += 1
        transition(
            session,
            job,
            JobStatus.FAILED_FINAL,
            worker_id=worker_id,
            detail={
                "error": payload,
                "reason": "attempts exhausted" if exhausted else "permanent error",
            },
        )
    record_event(session, job.id, JobEventType.ERROR, detail=payload, worker_id=worker_id)
    session.flush()
    return job


def block_job(
    session: Session,
    job: Job,
    reason: BlockedReason,
    remediation: dict[str, Any],
    *,
    worker_id: uuid.UUID | None = None,
) -> Job:
    """Park a job with an actionable reason instead of failing it (F-24)."""
    transition(
        session,
        job,
        JobStatus.BLOCKED,
        worker_id=worker_id,
        blocked_reason=reason,
        remediation=remediation,
        detail={"blocked_reason": reason.value, **remediation},
    )
    record_event(
        session,
        job.id,
        JobEventType.BLOCKED,
        detail={"reason": reason.value, **remediation},
        worker_id=worker_id,
    )
    session.flush()
    return job


def unblock_ready_dependents(session: Session) -> int:
    """Return dependency-blocked jobs to the queue once parents succeeded.

    A parent that reaches FAILED_FINAL leaves dependents BLOCKED rather than
    cancelling them: automatic cascade cancellation would silently destroy
    queued work the user may still want (ADR-0002 section 9).
    """
    blocked = session.execute(
        select(Job).where(
            Job.status == JobStatus.BLOCKED,
            Job.blocked_reason == BlockedReason.DEPENDENCY,
        )
    ).scalars()

    released = 0
    for job in blocked:
        parents = (
            session.execute(
                select(Job.status)
                .join(JobDependency, JobDependency.depends_on_job_id == Job.id)
                .where(JobDependency.job_id == job.id)
            )
            .scalars()
            .all()
        )
        if parents and all(status is JobStatus.SUCCEEDED for status in parents):
            transition(session, job, JobStatus.QUEUED, detail={"reason": "dependencies satisfied"})
            released += 1
    session.flush()
    return released


def touch_progress(session: Session, job_id: uuid.UUID, units_done: int) -> None:
    """Persist progress independently of any UI or API process (110.7)."""
    session.execute(
        update(Job).where(Job.id == job_id).values(units_done=units_done, updated_at=func.now())
    )


def _database_now(session: Session) -> dt.datetime:
    """Return PostgreSQL's clock for lease and scheduling decisions."""
    return session.execute(select(func.now())).scalar_one()
