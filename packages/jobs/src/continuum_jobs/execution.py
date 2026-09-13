"""Handler contract and the durable unit loop (ADR-0002 section 2).

**The central Phase 0 invariant lives here.** "Checkpoint often" is necessary
and insufficient: a worker that completes a unit and dies before the
checkpoint commits will re-run that unit on restart. If the unit's effect is
not repeat-safe, the system produces duplicates or corruption, and no
checkpoint policy can prevent it -- the window is between the effect and the
record of the effect.

What actually makes at-least-once execution behave as effectively-once:

1. every unit's effect is a **content-addressed write** (temp -> fsync ->
   atomic rename, so a repeat is a byte-identical no-op) or a
   **deterministic upsert** keyed by the input, never by an autoincrement;
2. the unit's completion row and the checkpoint advance commit in the **same
   transaction**;
3. the order is always: perform effect -> durably land it -> commit the
   completion record.

A crash anywhere then re-runs a unit whose effect is a no-op.

**The second invariant: no worker-owned write after ownership is lost.**
A worker can lose its job at any moment - its lease expires while it is
between statements, the reaper requeues the job, another worker claims it.
Checking ownership and then writing leaves a window between the two. So
every transaction that records worker-owned state (plan, step start, unit
completion with its lease renewal, unit failure, the final status) begins by
locking the job row and proving, under that lock, that this worker still
owns a RUNNING job (:func:`_hold`). The lock is held until that transaction
commits: no reaper or claim can take the job between the proof and the
writes that depend on it. A worker that cannot prove ownership rolls back
and stands down, recording only its own stand-down event (final audit
H-1/H-2). No lock is ever held while a handler runs.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Protocol, runtime_checkable

from continuum_core import ContinuumError, ErrorCategory, StructuredError
from continuum_db.enums import JobEventType, JobStatus, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobStep
from continuum_observability import correlation_scope, get_logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from continuum_jobs.lease import LeaseHeartbeat, renew_lease, worker_should_drain
from continuum_jobs.queue import (
    JobOwnershipLostError,
    StaleJobStateError,
    fail_job,
    lock_job,
    record_event,
    transition,
)

__all__ = [
    "JobContext",
    "JobHandler",
    "StopReason",
    "UnitOutcome",
    "UnitSpec",
    "execute_job",
    "plan_units",
    "record_ownership_loss",
]

#: Refusals meaning "this worker's view of the job is no longer the database's".
_LOST = (JobOwnershipLostError, StaleJobStateError)

log = get_logger("continuum.jobs.execution")


class StopReason(StrEnum):
    """Why the unit loop stopped before finishing all units."""

    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    DRAINED = "DRAINED"
    FAILED = "FAILED"
    OWNERSHIP_LOST = "OWNERSHIP_LOST"
    """This worker no longer owns the job and stopped without writing status.

    Someone else owns it now (the reaper reclaimed it, or its lease was
    renewed elsewhere), so writing status here would be the same two-writer
    violation the guarded transition table exists to prevent."""


@dataclass(frozen=True, slots=True)
class UnitSpec:
    """One durable unit of work.

    ``unit_key`` must be **deterministic**: re-planning the same job has to
    produce the same keys, or resume would not recognise completed work.
    ``ordinal`` is optional and only used by ordered streams (F-29).
    """

    unit_key: str
    ordinal: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UnitOutcome:
    """What a handler produced for one unit."""

    result: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] | None = None


@dataclass
class JobContext:
    """Everything a handler is given. Deliberately small."""

    job_id: uuid.UUID
    job_type: str
    payload: dict[str, Any]
    session: Session
    worker_id: uuid.UUID | None
    correlation_id: str | None
    #: Approved storage abstraction. A-02 permits the worker to use storage
    #: and provider modules; only durable *coordination* is PostgreSQL-only.
    derived: Any = None
    providers: Any = None

    def latest_checkpoint(self) -> dict[str, Any] | None:
        row = self.session.execute(
            select(JobCheckpoint)
            .where(JobCheckpoint.job_id == self.job_id)
            .order_by(JobCheckpoint.seq.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.payload if row else None


@runtime_checkable
class JobHandler(Protocol):
    """What a job type must implement.

    ``plan`` is separated from ``execute_unit`` so the unit list is durable
    before any work starts: resume then compares against stored rows rather
    than trusting a handler to recompute identical work.
    """

    job_type: ClassVar[str]

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        """Return the deterministic list of units for this job."""
        ...

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        """Perform one unit. MUST be safe to run more than once."""
        ...


def plan_units(session: Session, job: Job, units: Sequence[UnitSpec]) -> list[JobStep]:
    """Materialise the unit list, idempotently.

    Uses the ``(job_id, unit_key)`` unique constraint: re-planning after a
    crash adds only genuinely new units and never duplicates existing ones.
    """
    existing = {
        step.unit_key: step
        for step in session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars()
    }
    created: list[JobStep] = []
    for unit in units:
        if unit.unit_key in existing:
            continue
        step = JobStep(
            job_id=job.id,
            unit_key=unit.unit_key,
            ordinal=unit.ordinal,
            status=StepStatus.PENDING,
        )
        session.add(step)
        created.append(step)

    if job.units_total is None or job.units_total < len(units):
        job.units_total = len(units)
    session.flush()
    return created


def _completed_unit_keys(session: Session, job_id: uuid.UUID) -> set[str]:
    return set(
        session.execute(
            select(JobStep.unit_key).where(
                JobStep.job_id == job_id, JobStep.status == StepStatus.SUCCEEDED
            )
        ).scalars()
    )


def _next_checkpoint_seq(session: Session, job_id: uuid.UUID) -> int:
    current = session.execute(
        select(func.max(JobCheckpoint.seq)).where(JobCheckpoint.job_id == job_id)
    ).scalar_one_or_none()
    return int(current or 0) + 1


def execute_job(
    session: Session,
    job: Job,
    handler: JobHandler,
    *,
    worker_id: uuid.UUID | None = None,
    lease_seconds: int = 30,
    derived: Any = None,
    providers: Any = None,
    force_rerun_completed: bool = False,
    settings: Any = None,
    heartbeat_seconds: float = 5.0,
) -> StopReason:
    """Run a job's units to completion, or stop cooperatively.

    With ``worker_id`` (always, in production) every worker-owned write is
    guarded by :func:`_hold`; losing the job at any point ends in
    ``OWNERSHIP_LOST`` with nothing written for it. Without ``worker_id``
    (tests and tools that execute a job directly) rows are still locked and
    transitions still refuse stale state, but there is no lease to prove.

    ``force_rerun_completed`` exists only for acceptance test 110.10, which
    must prove that re-executing an already-completed unit is a byte-identical
    no-op producing no duplicate row or effect. Production never sets it.
    """
    ctx = JobContext(
        job_id=job.id,
        job_type=job.job_type,
        payload=job.payload or {},
        session=session,
        worker_id=worker_id,
        correlation_id=job.correlation_id,
        derived=derived,
        providers=providers,
    )

    with correlation_scope(job.correlation_id):
        try:
            units = list(handler.plan(ctx))
            _hold(session, job, worker_id)
            plan_units(session, job, units)
            session.commit()
        except _LOST:
            return _stand_down(session, job.id, worker_id)
        except Exception as exc:
            session.rollback()
            return _record_failure(session, job, _structured(exc), worker_id)

        already_done = set() if force_rerun_completed else _completed_unit_keys(session, job.id)
        started = dt.datetime.now(dt.UTC)

        for index, unit in enumerate(units):
            if unit.unit_key in already_done:
                continue

            # ---- 0. stop check and step start, under the ownership lock --
            try:
                _hold(session, job, worker_id)
                stop = _stop_requested(session, job, worker_id)
                if stop is not None:
                    _land_stop(session, job, stop, worker_id)
                    session.commit()
                    return stop

                step = session.execute(
                    select(JobStep).where(
                        JobStep.job_id == job.id, JobStep.unit_key == unit.unit_key
                    )
                ).scalar_one()
                step.status = StepStatus.RUNNING
                step.started_at = dt.datetime.now(dt.UTC)
                step.attempt += 1
                record_event(
                    session, job.id, JobEventType.STEP_STARTED, detail={"unit_key": unit.unit_key}
                )
                session.commit()
            except _LOST:
                return _stand_down(session, job.id, worker_id)

            # ---- 1. perform the effect (must be repeat-safe) --------------
            # No row lock is held here. The lease is renewed on a background
            # thread FOR THE DURATION of the unit, not just between units.
            # Without this, a unit outliving its lease is reaped and run
            # concurrently by a second worker.
            beat: LeaseHeartbeat | None = None
            try:
                if worker_id is not None and settings is not None:
                    with LeaseHeartbeat(
                        settings,
                        job_id=job.id,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                        interval_seconds=heartbeat_seconds,
                    ) as beat:
                        outcome = handler.execute_unit(ctx, unit)
                else:
                    outcome = handler.execute_unit(ctx, unit)
            except Exception as exc:
                # Provider/policy blocks are decisions, not failed attempts.
                # The standalone worker owns the transition to BLOCKED and
                # its actionable remediation payload; it proves ownership
                # the same way before parking the job.
                if isinstance(exc, ContinuumError) and exc.context.get("blocked_reason"):
                    raise
                if beat is not None and beat.ownership_lost:
                    return _stand_down(session, job.id, worker_id)
                return _record_failure(
                    session, job, _structured(exc), worker_id, step=step, unit_key=unit.unit_key
                )

            if beat is not None and beat.ownership_lost:
                # The effect already landed and is content-addressed, so the
                # rightful owner's re-run is a byte-identical no-op. What must
                # NOT happen is this worker writing progress or status for a
                # job it no longer owns.
                return _stand_down(session, job.id, worker_id)

            # ---- 2. completion record + checkpoint + lease, ONE transaction
            try:
                _hold(session, job, worker_id)
                step.status = StepStatus.SUCCEEDED
                step.result = outcome.result
                step.completed_at = dt.datetime.now(dt.UTC)
                job.units_done = len(_completed_unit_keys(session, job.id) | {unit.unit_key})
                job.current_step = index + 1
                job.elapsed_active_ms = int(
                    (dt.datetime.now(dt.UTC) - started).total_seconds() * 1000
                )

                if outcome.checkpoint is not None:
                    session.add(
                        JobCheckpoint(
                            job_id=job.id,
                            seq=_next_checkpoint_seq(session, job.id),
                            payload=outcome.checkpoint,
                        )
                    )
                    record_event(
                        session,
                        job.id,
                        JobEventType.CHECKPOINT,
                        detail={"unit_key": unit.unit_key},
                    )

                record_event(
                    session,
                    job.id,
                    JobEventType.STEP_COMPLETED,
                    detail={"unit_key": unit.unit_key, "units_done": job.units_done},
                    worker_id=worker_id,
                )
                if worker_id is not None and not renew_lease(
                    session, job.id, lease_seconds, worker_id=worker_id
                ):  # pragma: no cover - impossible while _hold's lock is held
                    raise JobOwnershipLostError(
                        "This worker no longer owns the job.",
                        technical_detail=f"job_id={job.id} lease renewal refused under lock",
                    )
                session.commit()
            except _LOST:
                return _stand_down(session, job.id, worker_id)

        # ---- 3. final status, proven under the same lock ------------------
        try:
            _hold(session, job, worker_id)
            transition(session, job, JobStatus.SUCCEEDED, worker_id=worker_id, owner=worker_id)
            session.commit()
        except _LOST:
            return _stand_down(session, job.id, worker_id)
        return StopReason.COMPLETED


def _hold(session: Session, job: Job, worker_id: uuid.UUID | None) -> None:
    """Lock the job row for this transaction and prove this worker owns it.

    Called at the start of every transaction that records worker-owned state,
    before anything is written. The row stays locked until that transaction
    commits or rolls back, so the proof and the writes it permits are
    atomic: a reaper or another worker cannot take the job in between.

    Raises :class:`JobOwnershipLostError` unless the committed row is RUNNING
    with this worker as ``lease_owner``. Without ``worker_id`` the row is
    locked but there is no lease to prove.
    """
    status, owner = lock_job(session, job)
    if worker_id is not None and (owner != worker_id or status is not JobStatus.RUNNING):
        raise JobOwnershipLostError(
            "This worker no longer owns the job.",
            technical_detail=(
                f"job_id={job.id} worker={worker_id} lease_owner={owner} status={status.value}"
            ),
            remediation="Stand down; the job's current owner will finish it.",
        )


def _stand_down(session: Session, job_id: uuid.UUID, worker_id: uuid.UUID | None) -> StopReason:
    """Discard everything this transaction held and record only the stand-down.

    A worker without a lease has no ownership to lose; a refusal then means
    the caller's view is stale, which is reported rather than hidden.
    """
    session.rollback()
    if worker_id is None:
        raise StaleJobStateError(
            "The job changed underneath its execution.",
            technical_detail=f"job_id={job_id}",
            remediation="Reload the job and run it again.",
        )
    record_ownership_loss(session, job_id, worker_id)
    session.commit()
    return StopReason.OWNERSHIP_LOST


def _record_failure(
    session: Session,
    job: Job,
    error: StructuredError,
    worker_id: uuid.UUID | None,
    *,
    step: JobStep | None = None,
    unit_key: str | None = None,
) -> StopReason:
    """Record a failed plan or unit - only if this worker still owns the job.

    Ownership is proven under the row lock before the step, the attempt
    counter, the error history or the status are touched (final audit H-2).
    """
    try:
        _hold(session, job, worker_id)
        if step is not None:
            step.status = StepStatus.FAILED
            step.last_error = error.to_dict()
            step.completed_at = dt.datetime.now(dt.UTC)
            record_event(
                session,
                job.id,
                JobEventType.STEP_FAILED,
                detail={"unit_key": unit_key, "error": error.to_dict()},
                worker_id=worker_id,
            )
        fail_job(session, job, error, worker_id=worker_id, owner=worker_id)
        session.commit()
    except _LOST:
        return _stand_down(session, job.id, worker_id)
    return StopReason.FAILED


def record_ownership_loss(session: Session, job_id: uuid.UUID, worker_id: uuid.UUID | None) -> None:
    """Audit that this worker stood down. Deliberately writes no status.

    Appending an event is safe even though the job belongs to someone else:
    it changes nothing the owner reads or writes, and it does not lock the
    job row against them.
    """
    record_event(
        session,
        job_id,
        JobEventType.LEASE_EXPIRED,
        detail={"reason": "ownership lost; worker stood down without writing status"},
        worker_id=worker_id,
    )
    log.warning(
        "stood down: this worker no longer owns the job",
        extra={"job_id": str(job_id), "worker_id": str(worker_id)},
    )


def _stop_requested(session: Session, job: Job, worker_id: uuid.UUID | None) -> StopReason | None:
    """Cooperative stop check, run between units, never mid-unit.

    Called with the row already locked by :func:`_hold`, so the flags read
    here cannot change before the stop they cause has landed.
    """
    session.refresh(job, attribute_names=["cancel_requested", "pause_requested"])
    if job.cancel_requested:
        return StopReason.CANCELLED
    if job.pause_requested:
        return StopReason.PAUSED
    if worker_id is not None and worker_should_drain(session, worker_id):
        return StopReason.DRAINED
    return None


def _land_stop(session: Session, job: Job, reason: StopReason, worker_id: uuid.UUID | None) -> None:
    """Move a stopped job to its resting state, leaving it resumable."""
    if reason is StopReason.CANCELLED:
        if job.status is JobStatus.RUNNING:
            transition(session, job, JobStatus.CANCELLING, worker_id=worker_id, owner=worker_id)
        transition(session, job, JobStatus.CANCELLED, worker_id=worker_id, owner=worker_id)
        return

    # Pause and drain both leave the job resumable from its completed units.
    if job.status is JobStatus.RUNNING:
        transition(session, job, JobStatus.PAUSING, worker_id=worker_id, owner=worker_id)
    if reason is StopReason.PAUSED:
        transition(session, job, JobStatus.PAUSED, worker_id=worker_id, owner=worker_id)
    else:
        # Drain: the worker is going away, not the job. Return it to the
        # queue so another worker (or this one after restart) picks it up.
        transition(
            session,
            job,
            JobStatus.PAUSED,
            worker_id=worker_id,
            owner=worker_id,
            detail={"reason": "worker drain"},
        )
        transition(
            session,
            job,
            JobStatus.QUEUED,
            owner=worker_id,
            detail={"reason": "requeued after drain"},
        )
    job.lease_owner = None
    job.lease_expires_at = None
    session.flush()


def _structured(exc: BaseException) -> StructuredError:
    """Convert any exception into the structured form stored on the job."""
    if isinstance(exc, ContinuumError):
        return exc.structured()
    return StructuredError(
        code="handler.unhandled_exception",
        category=ErrorCategory.RETRYABLE_TRANSIENT,
        user_message="The job failed with an unexpected error.",
        technical_detail=f"{type(exc).__name__}: {exc}",
        remediation="Inspect the job event log for the failing unit.",
    )
