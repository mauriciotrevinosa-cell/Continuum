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

from continuum_jobs.lease import renew_lease, worker_should_drain
from continuum_jobs.queue import fail_job, record_event, transition

__all__ = [
    "JobContext",
    "JobHandler",
    "StopReason",
    "UnitOutcome",
    "UnitSpec",
    "execute_job",
    "plan_units",
]

log = get_logger("continuum.jobs.execution")


class StopReason(StrEnum):
    """Why the unit loop stopped before finishing all units."""

    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    DRAINED = "DRAINED"
    FAILED = "FAILED"


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
) -> StopReason:
    """Run a job's units to completion, or stop cooperatively.

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
            plan_units(session, job, units)
            session.commit()
        except Exception as exc:
            fail_job(session, job, _structured(exc), worker_id=worker_id)
            session.commit()
            return StopReason.FAILED

        already_done = set() if force_rerun_completed else _completed_unit_keys(session, job.id)
        started = dt.datetime.now(dt.UTC)

        for index, unit in enumerate(units):
            if unit.unit_key in already_done:
                continue

            stop = _stop_requested(session, job, worker_id)
            if stop is not None:
                _land_stop(session, job, stop, worker_id)
                session.commit()
                return stop

            step = session.execute(
                select(JobStep).where(JobStep.job_id == job.id, JobStep.unit_key == unit.unit_key)
            ).scalar_one()

            step.status = StepStatus.RUNNING
            step.started_at = dt.datetime.now(dt.UTC)
            step.attempt += 1
            session.commit()
            record_event(
                session, job.id, JobEventType.STEP_STARTED, detail={"unit_key": unit.unit_key}
            )

            try:
                # ---- 1. perform the effect (must be repeat-safe) ----------
                outcome = handler.execute_unit(ctx, unit)
            except Exception as exc:
                # Provider/policy blocks are decisions, not failed attempts.
                # The standalone worker owns the transition to BLOCKED and
                # its actionable remediation payload.
                if isinstance(exc, ContinuumError) and exc.context.get("blocked_reason"):
                    raise
                step.status = StepStatus.FAILED
                error = _structured(exc)
                step.last_error = error.to_dict()
                step.completed_at = dt.datetime.now(dt.UTC)
                record_event(
                    session,
                    job.id,
                    JobEventType.STEP_FAILED,
                    detail={"unit_key": unit.unit_key, "error": error.to_dict()},
                    worker_id=worker_id,
                )
                fail_job(session, job, error, worker_id=worker_id)
                session.commit()
                return StopReason.FAILED

            # ---- 2. completion record + checkpoint in ONE transaction -----
            step.status = StepStatus.SUCCEEDED
            step.result = outcome.result
            step.completed_at = dt.datetime.now(dt.UTC)
            job.units_done = len(_completed_unit_keys(session, job.id) | {unit.unit_key})
            job.current_step = index + 1
            job.elapsed_active_ms = int((dt.datetime.now(dt.UTC) - started).total_seconds() * 1000)

            if outcome.checkpoint is not None:
                session.add(
                    JobCheckpoint(
                        job_id=job.id,
                        seq=_next_checkpoint_seq(session, job.id),
                        payload=outcome.checkpoint,
                    )
                )
                record_event(
                    session, job.id, JobEventType.CHECKPOINT, detail={"unit_key": unit.unit_key}
                )

            record_event(
                session,
                job.id,
                JobEventType.STEP_COMPLETED,
                detail={"unit_key": unit.unit_key, "units_done": job.units_done},
                worker_id=worker_id,
            )
            session.commit()

            if worker_id is not None:
                renew_lease(session, job.id, lease_seconds)
                session.commit()

        transition(session, job, JobStatus.SUCCEEDED, worker_id=worker_id)
        session.commit()
        return StopReason.COMPLETED


def _stop_requested(session: Session, job: Job, worker_id: uuid.UUID | None) -> StopReason | None:
    """Cooperative stop check, run between units, never mid-unit."""
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
            transition(session, job, JobStatus.CANCELLING, worker_id=worker_id)
        transition(session, job, JobStatus.CANCELLED, worker_id=worker_id)
        return

    # Pause and drain both leave the job resumable from its completed units.
    if job.status is JobStatus.RUNNING:
        transition(session, job, JobStatus.PAUSING, worker_id=worker_id)
    if reason is StopReason.PAUSED:
        transition(session, job, JobStatus.PAUSED, worker_id=worker_id)
    else:
        # Drain: the worker is going away, not the job. Return it to the
        # queue so another worker (or this one after restart) picks it up.
        transition(
            session, job, JobStatus.PAUSED, worker_id=worker_id, detail={"reason": "worker drain"}
        )
        transition(session, job, JobStatus.QUEUED, detail={"reason": "requeued after drain"})
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
