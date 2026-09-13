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

from continuum_core import ContinuumError, ErrorCategory, StructuredError, content_hash_bytes, uuid7
from continuum_db.enums import BlockedReason, JobEventType, JobStatus
from continuum_db.models import Job, JobDependency, JobEvent
from continuum_observability import current_correlation_id, get_logger
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from continuum_jobs.states import assert_transition, is_terminal, next_backoff_seconds

__all__ = [
    "DependencyCycleError",
    "JobOwnershipLostError",
    "StaleJobStateError",
    "add_dependency",
    "apply_pending_requests",
    "block_job",
    "claim_next_job",
    "compute_dedupe_key",
    "enqueue",
    "fail_job",
    "lock_job",
    "record_event",
    "request_cancel",
    "request_pause",
    "resume_job",
    "retry_job",
    "transition",
    "unblock_ready_dependents",
]

log = get_logger("continuum.jobs.queue")

# Dependency reachability and edge insertion must be one serial graph
# mutation across every API/worker process. PostgreSQL transaction-scoped
# advisory locks release automatically on commit/rollback and avoid adding a
# schema object solely to lock an otherwise empty graph.
_DEPENDENCY_GRAPH_LOCK = 0x434F4E5444455047  # "CONTDEPG"


class DependencyCycleError(ContinuumError):
    """A proposed dependency edge would close a ring in the job DAG."""

    code = "jobs.dependency_cycle"
    category = ErrorCategory.PERMANENT_INPUT


class JobOwnershipLostError(ContinuumError):
    """The worker asserting ownership of a job no longer holds its lease.

    Raised before anything is written. The worker that sees it must stand
    down: the job belongs to someone else now (reaped, claimed elsewhere, or
    finished), so any status, progress or retry bookkeeping it wrote would
    overwrite the rightful owner's.
    """

    code = "jobs.ownership_lost"
    category = ErrorCategory.RETRYABLE_TRANSIENT


class StaleJobStateError(ContinuumError):
    """A transition was attempted from a view of the job the database no
    longer holds.

    The caller's object says one status or owner; the committed row says
    another. Applying the transition anyway would overwrite a newer state with
    a decision made on an older one, so it is refused before anything is
    written. Reload the job and decide again.
    """

    code = "jobs.stale_state"
    category = ErrorCategory.RETRYABLE_TRANSIENT


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
        add_dependency(session, job.id, parent_id)
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


def lock_job(session: Session, job: Job) -> tuple[JobStatus, uuid.UUID | None]:
    """Lock the job's row until this transaction ends; return its committed
    status and lease owner.

    ``FOR NO KEY UPDATE``: it excludes every other writer of the row (a
    worker, the reaper's and the claim's ``FOR UPDATE SKIP LOCKED``, a lease
    renewal) while still letting unrelated inserts that merely reference the
    job - audit events, steps - proceed.

    Autoflush is suspended so that nothing the caller has changed in memory
    reaches the database before the lock has been taken and checked.
    """
    with session.no_autoflush:
        row = session.execute(
            select(Job.status, Job.lease_owner)
            .where(Job.id == job.id)
            .with_for_update(key_share=True)
        ).one_or_none()
    if row is None:
        raise StaleJobStateError(
            "This job no longer exists.",
            technical_detail=f"job_id={job.id}",
            remediation="Reload the job list.",
        )
    return row.status, row.lease_owner


def _believed(job: Job, attribute: str) -> Any:
    """The value this session last loaded or flushed for ``attribute``.

    Pending in-memory edits are ignored on purpose: the reaper, for instance,
    clears ``lease_owner`` before it transitions. What matters is whether the
    decision was made on the row the database still holds.
    """
    history = inspect(job).attrs[attribute].load_history()
    if history.deleted:
        return history.deleted[0]
    if history.unchanged:
        return history.unchanged[0]
    return history.added[0] if history.added else None


def transition(
    session: Session,
    job: Job,
    target: JobStatus,
    *,
    worker_id: uuid.UUID | None = None,
    owner: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    blocked_reason: BlockedReason | None = None,
    remediation: dict[str, Any] | None = None,
) -> Job:
    """Move a job to ``target``: the single, database-guarded status writer.

    Three checks, all against the **locked committed row**, never against the
    caller's object alone (ADR-0002 section 4, final-audit H-3):

    1. ``owner`` - when given, the caller claims to be the worker executing
       this job; the row's ``lease_owner`` must still be that worker, or
       :class:`JobOwnershipLostError` is raised;
    2. freshness - the status and lease owner this session believes must be
       the ones the row holds, or :class:`StaleJobStateError` is raised. A
       decision made on a stale object (``expire_on_commit=False`` keeps
       objects across commits) must not overwrite what another worker, the
       reaper or the API has committed since;
    3. the transition table, applied to the row's actual status.

    The row lock is held until the caller's transaction ends, so the checks
    and the write cannot be separated by another writer.

    ``worker_id`` only attributes the audit event; it asserts nothing.
    """
    current, current_owner = lock_job(session, job)
    if owner is not None and current_owner != owner:
        raise JobOwnershipLostError(
            "This worker no longer owns the job.",
            technical_detail=(
                f"job_id={job.id} caller={owner} lease_owner={current_owner} "
                f"status={current.value} target={target.value}"
            ),
            remediation="Stand down; the job's current owner will finish it.",
        )
    with session.no_autoflush:
        believed = (_believed(job, "status"), _believed(job, "lease_owner"))
    if believed != (current, current_owner):
        raise StaleJobStateError(
            "The job changed since it was loaded.",
            technical_detail=(
                f"job_id={job.id} believed status={believed[0]} owner={believed[1]}; "
                f"committed status={current.value} owner={current_owner}; target={target.value}"
            ),
            remediation="Reload the job and try again.",
        )
    assert_transition(current, target, job_id=job.id)
    previous = current
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
            # Belt and braces alongside apply_pending_requests(): never start
            # work the user has already asked to stop, even if the request
            # landed between the request-applier pass and this claim.
            Job.cancel_requested.is_(False),
            Job.pause_requested.is_(False),
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
    """Set the pause FLAG, and only the flag.

    **Callers of this are the API.** It must not write ``status`` — the
    approved rule (FOUNDATION_APPROVAL invariant 8, ADR-0002 section 4) is
    that API calls set request flags and worker/reaper paths own every
    guarded status transition.

    An earlier version transitioned QUEUED -> PAUSED and RUNNING -> PAUSING
    here, which reintroduced exactly the two-writer race F-28 exists to
    prevent. :func:`apply_pending_requests` now performs those transitions on
    the worker side; a RUNNING job is landed cooperatively by its own
    execution loop.
    """
    job.pause_requested = True
    record_event(session, job.id, JobEventType.PAUSE_REQUESTED)
    session.flush()
    return job


def request_cancel(session: Session, job: Job) -> Job:
    """Set the cancel FLAG, and only the flag. See :func:`request_pause`."""
    job.cancel_requested = True
    record_event(session, job.id, JobEventType.CANCEL_REQUESTED)
    session.flush()
    return job


def apply_pending_requests(session: Session) -> dict[str, int]:
    """Act on pause/cancel flags. **Worker- and reaper-owned.**

    Handles jobs that are *not* currently executing: a RUNNING job observes
    its own flags between units and lands itself (``execution._land_stop``).
    Everything else needs someone to notice, and that someone must be a
    worker path so there is exactly one writer of ``status``.

    Returns a count per action so the worker can log a meaningful summary.
    """
    counts = {"cancelled": 0, "paused": 0}

    # Rows are locked as they are selected, as the claim and the reaper do:
    # each decision is then made on the row as committed, never on a snapshot
    # another worker's pass or a claim could supersede before the write.
    # SKIP LOCKED leaves a row another writer holds to that writer.
    cancellable = (
        session.execute(
            select(Job)
            .where(
                Job.cancel_requested.is_(True),
                Job.status.in_(
                    (
                        JobStatus.QUEUED,
                        JobStatus.PAUSED,
                        JobStatus.BLOCKED,
                        JobStatus.FAILED_RETRYABLE,
                    )
                ),
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for job in cancellable:
        transition(session, job, JobStatus.CANCELLED, detail={"reason": "cancel requested"})
        counts["cancelled"] += 1

    pausable = (
        session.execute(
            select(Job)
            .where(
                Job.pause_requested.is_(True),
                Job.cancel_requested.is_(False),
                Job.status == JobStatus.QUEUED,
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )
    for job in pausable:
        transition(session, job, JobStatus.PAUSED, detail={"reason": "pause requested"})
        counts["paused"] += 1

    session.flush()
    return counts


def add_dependency(
    session: Session,
    job_id: uuid.UUID,
    depends_on_job_id: uuid.UUID,
    *,
    kind: str = "completion",
) -> JobDependency:
    """Add a DAG edge, rejecting anything that would create a cycle.

    ADR-0002 section 9 requires a cycle check at insert. The database CHECK
    constraint only catches the self-edge ``A -> A``; a transitive cycle
    (``A -> B -> C -> A``) would otherwise be accepted and would deadlock the
    scheduler permanently, because every job in the ring waits for another
    member that can never finish.

    The reachability query is a recursive CTE rather than a Python walk so the
    whole check happens in one round trip and sees the same snapshot as the
    insert.
    """
    if job_id == depends_on_job_id:
        raise DependencyCycleError(
            "A job cannot depend on itself.",
            technical_detail=f"job_id == depends_on_job_id == {job_id}",
        )

    # A serial reachability check is insufficient: two transactions can each
    # observe the graph before the other's insert and jointly commit a cycle.
    # Hold this PostgreSQL-wide transaction lock through both the check and
    # insert so the next mutator sees every previously committed edge.
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _DEPENDENCY_GRAPH_LOCK},
    )

    if _creates_cycle(session, job_id=job_id, depends_on_job_id=depends_on_job_id):
        raise DependencyCycleError(
            "That dependency would create a cycle, which could never complete.",
            technical_detail=(f"{depends_on_job_id} already depends (transitively) on {job_id}"),
            remediation=(
                "Remove the opposing dependency first, or restructure the jobs so the "
                "graph stays acyclic."
            ),
        )

    edge = JobDependency(job_id=job_id, depends_on_job_id=depends_on_job_id, kind=kind)
    session.add(edge)
    session.flush()
    return edge


def _creates_cycle(session: Session, *, job_id: uuid.UUID, depends_on_job_id: uuid.UUID) -> bool:
    """True if ``job_id`` is already reachable from ``depends_on_job_id``.

    Adding ``job_id -> depends_on_job_id`` closes a ring exactly when the
    proposed prerequisite already depends on the dependent.
    """
    reachable = text(
        """
        WITH RECURSIVE reach(id) AS (
            SELECT depends_on_job_id FROM job_dependency WHERE job_id = :start
            UNION
            SELECT d.depends_on_job_id
              FROM job_dependency d
              JOIN reach r ON d.job_id = r.id
        )
        SELECT 1 FROM reach WHERE id = :target LIMIT 1
        """
    )
    found = session.execute(
        reachable, {"start": depends_on_job_id, "target": job_id}
    ).scalar_one_or_none()
    return found is not None


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
    session: Session,
    job: Job,
    error: StructuredError,
    *,
    worker_id: uuid.UUID | None = None,
    owner: uuid.UUID | None = None,
) -> Job:
    """Record a structured failure and decide retryable vs final (F-25, F-70).

    ``owner``: the executing worker. Ownership is proven under the row lock
    *before* any failure bookkeeping is touched, so a worker that has lost
    the job cannot increment its attempt or overwrite its error history.
    """
    if owner is not None:
        _, current_owner = lock_job(session, job)
        if current_owner != owner:
            raise JobOwnershipLostError(
                "This worker no longer owns the job.",
                technical_detail=f"job_id={job.id} caller={owner} lease_owner={current_owner}",
                remediation="Stand down; the job's current owner will finish it.",
            )
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
            owner=owner,
            detail={"error": payload, "retry_in_seconds": round(delay, 2)},
        )
    else:
        job.attempt += 1
        transition(
            session,
            job,
            JobStatus.FAILED_FINAL,
            worker_id=worker_id,
            owner=owner,
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
    owner: uuid.UUID | None = None,
) -> Job:
    """Park a job with an actionable reason instead of failing it (F-24).

    ``owner``: the executing worker, when a running job is parked; see
    :func:`transition`.
    """
    transition(
        session,
        job,
        JobStatus.BLOCKED,
        worker_id=worker_id,
        owner=owner,
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
    # Locked as selected (see apply_pending_requests): a job cancelled by
    # another worker's pass must not be released from a snapshot.
    blocked = (
        session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.BLOCKED,
                Job.blocked_reason == BlockedReason.DEPENDENCY,
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

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


def _database_now(session: Session) -> dt.datetime:
    """Return PostgreSQL's clock for lease and scheduling decisions."""
    return session.execute(select(func.now())).scalar_one()
