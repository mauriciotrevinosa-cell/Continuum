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

from continuum_jobs.lease import LeaseHeartbeat, renew_lease, worker_should_drain
from continuum_jobs.queue import (
    OwnershipLostError,
    assert_owner,
    fail_job,
    lock_job_row,
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
]

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
            units = _plan_under_lease(
                session,
                job,
                handler,
                ctx,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                settings=settings,
                heartbeat_seconds=heartbeat_seconds,
            )
        except OwnershipLostError:
            # H-5b: losing the lease is a stand-down, never a crash. This
            # used to escape execute_job() entirely -- nothing in the worker
            # loop or run_forever() catches it -- so a routine race (a slow
            # plan whose lease is reaped) killed the worker process instead
            # of yielding the job to its rightful owner.
            session.rollback()
            record_ownership_loss(session, job.id, worker_id)
            session.commit()
            return StopReason.OWNERSHIP_LOST
        except Exception as exc:
            # H-5b: ownership dominates the planning failure too. The
            # handler's error is real, but a worker that no longer owns the
            # job has no standing to declare it failed, and writing that
            # failure would corrupt the rightful owner's row. The rollback
            # first discards anything the failed handler left pending, so
            # the ownership probe's flush cannot push it.
            session.rollback()
            if worker_id is not None and not _still_owns(session, job.id, worker_id):
                session.rollback()
                record_ownership_loss(session, job.id, worker_id)
                session.commit()
                return StopReason.OWNERSHIP_LOST
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
                if stop is StopReason.OWNERSHIP_LOST:
                    record_ownership_loss(session, job.id, worker_id)
                    session.commit()
                    return stop
                _land_stop(session, job, stop, worker_id)
                session.commit()
                return stop

            # H-6: authorise the effect while the row lock is STILL HELD.
            # Proving ownership is not enough on its own -- the proof is a
            # statement about the past the moment the lock is released, and
            # the first heartbeat beat is a whole interval away. Renewing
            # here, under the lock, is what makes this worker the executor
            # for a bounded, known-live window rather than merely its last
            # recorded owner.
            if worker_id is not None and not _authorize_effect(
                session, job.id, worker_id, lease_seconds
            ):
                session.rollback()
                record_ownership_loss(session, job.id, worker_id)
                session.commit()
                return StopReason.OWNERSHIP_LOST

            # H-4: _stop_requested() above took the job row lock and did
            # NOT release it, so the ownership proof, the lease renewal and
            # this step-start write are one serialization unit -- the lock
            # is held right through to the commit below. Nothing may commit
            # between them; doing so would reopen exactly the window in
            # which a stale worker stamped status, started_at and attempt
            # onto the rightful owner's step row.
            step = session.execute(
                select(JobStep).where(JobStep.job_id == job.id, JobStep.unit_key == unit.unit_key)
            ).scalar_one()

            lost_ownership = False
            step.status = StepStatus.RUNNING
            step.started_at = dt.datetime.now(dt.UTC)
            step.attempt += 1
            session.commit()
            record_event(
                session, job.id, JobEventType.STEP_STARTED, detail={"unit_key": unit.unit_key}
            )

            beat: LeaseHeartbeat | None = None
            try:
                # ---- 1. perform the effect (must be repeat-safe) ----------
                # The lease is renewed on a background thread FOR THE DURATION
                # of the unit, not just between units. Without this, a unit
                # outliving its lease is reaped and run concurrently by a
                # second worker.
                if worker_id is not None and settings is not None:
                    with LeaseHeartbeat(
                        settings,
                        job_id=job.id,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                        interval_seconds=heartbeat_seconds,
                    ) as beat:
                        # H-6, last gate: the effect does not begin unless
                        # this worker is STILL the live owner. The two
                        # layers above -- refusing a lapsed lease and
                        # renewing under the row lock -- make this
                        # unreachable in production, because the job leaves
                        # that commit with a lease good for the whole
                        # lease_seconds and a heartbeat now running. What
                        # this catches is a stall between the authorising
                        # commit and the effect's first instruction, which
                        # is the same hazard that produced H-6 one step
                        # earlier. Defence in depth, not the guarantee.
                        #
                        # Deliberately a plain SELECT on its own session:
                        # see _owns_live_lease for why neither a lock nor
                        # the executing session may be used here.
                        if not _owns_live_lease(settings, job.id, worker_id):
                            session.rollback()
                            record_ownership_loss(session, job.id, worker_id)
                            session.commit()
                            return StopReason.OWNERSHIP_LOST
                        outcome = handler.execute_unit(ctx, unit)
                        lost_ownership = beat.ownership_lost
                else:
                    outcome = handler.execute_unit(ctx, unit)
            except Exception as exc:
                # OWNERSHIP LOSS DOMINATES *EVERY* EXCEPTION (final audit
                # H-2, cold audit H-7). If the heartbeat already proved this
                # worker no longer owns the job, the handler's failure is
                # this worker's private problem. Writing STEP_FAILED, error
                # history, attempts or a failure status here would corrupt
                # the NEW owner's job with an error that has nothing to do
                # with their execution.
                #
                # This check must come FIRST, ahead of the blocked-reason
                # re-raise below. When it did not, a stale worker's provider
                # block propagated into Worker.run_once(), which called
                # block_job() for a job it no longer owned; that raised
                # OwnershipLostError, and nothing in run_once() or
                # run_forever() catches it, so a routine race killed the
                # worker process.
                if worker_id is not None and (
                    (beat is not None and beat.ownership_lost)
                    or not _still_owns(session, job.id, worker_id)
                ):
                    session.rollback()
                    record_ownership_loss(session, job.id, worker_id)
                    session.commit()
                    log.warning(
                        "handler raised after ownership was lost; failure not recorded",
                        extra={"job_id": str(job.id), "worker_id": str(worker_id)},
                    )
                    return StopReason.OWNERSHIP_LOST

                # Provider/policy blocks are decisions, not failed attempts.
                # The standalone worker owns the transition to BLOCKED and
                # its actionable remediation payload -- but only while it
                # still owns the job, which the check above has now proved.
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
                try:
                    fail_job(session, job, error, worker_id=worker_id, require_owner=worker_id)
                except OwnershipLostError:
                    session.rollback()
                    record_ownership_loss(session, job.id, worker_id)
                    session.commit()
                    return StopReason.OWNERSHIP_LOST
                session.commit()
                return StopReason.FAILED

            # ---- 2. completion record + checkpoint in ONE transaction -----
            if lost_ownership:
                # The effect already landed and is content-addressed, so the
                # rightful owner's re-run is a byte-identical no-op. What must
                # NOT happen is this worker writing progress or status for a
                # job it no longer owns.
                session.rollback()
                record_ownership_loss(session, job.id, worker_id)
                session.commit()
                return StopReason.OWNERSHIP_LOST

            # H-1: take the row lock and re-prove ownership BEFORE writing
            # any of the unit's durable record. The lock is held until the
            # commit below, so nothing can reclaim the job in between --
            # the check and the write are one serialization unit rather
            # than two racing statements.
            if worker_id is not None:
                try:
                    assert_owner(session, job.id, worker_id, action="complete unit")
                except OwnershipLostError:
                    session.rollback()
                    record_ownership_loss(session, job.id, worker_id)
                    session.commit()
                    return StopReason.OWNERSHIP_LOST

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
                # Owner-scoped, and the answer is acted on. Renewing by job
                # id alone would extend whichever worker now owns the row.
                if not renew_lease(session, job.id, lease_seconds, worker_id=worker_id):
                    session.rollback()
                    record_ownership_loss(session, job.id, worker_id)
                    session.commit()
                    return StopReason.OWNERSHIP_LOST
                session.commit()

        # Final status is the last thing a stale worker could corrupt, so
        # it carries the same ownership requirement as every other write.
        try:
            transition(
                session,
                job,
                JobStatus.SUCCEEDED,
                worker_id=worker_id,
                require_owner=worker_id,
            )
        except OwnershipLostError:
            session.rollback()
            record_ownership_loss(session, job.id, worker_id)
            session.commit()
            return StopReason.OWNERSHIP_LOST
        session.commit()
        return StopReason.COMPLETED


def _plan_under_lease(
    session: Session,
    job: Job,
    handler: JobHandler,
    ctx: JobContext,
    *,
    worker_id: uuid.UUID | None,
    lease_seconds: int,
    settings: Any,
    heartbeat_seconds: float,
) -> list[UnitSpec]:
    """Plan a job's units without ever letting a stale planner write.

    Planning is unbounded, handler-controlled time that used to run with no
    lease maintenance and no ownership re-check (re-audit H-5). A slow plan
    was therefore *expected* to outlive its lease, not merely able to, and
    the planner would then still create ``JobStep`` rows and set
    ``units_total`` on a job another worker already owned. That damage
    outlived the moment, because ``plan_units`` skips unit keys that already
    exist and only ever grows ``units_total``: the stale plan was silently
    pinned in place for the rightful owner to execute.

    Two mechanisms, and neither alone is sufficient:

    1. a **heartbeat for the duration of** ``plan()``, so an honest slow
       planner keeps the lease it legitimately holds instead of being reaped
       mid-thought; and
    2. a **fresh ownership proof under the row lock**, taken after ``plan()``
       returns and released only by the commit that lands the plan.

    The heartbeat narrows the window; only the lock closes it. Ownership can
    still be lost while planning -- the process may be descheduled, or the
    database briefly unreachable past the lease window -- and at that moment
    the heartbeat is precisely what notices and says so.

    The lock is taken **after** the heartbeat thread has stopped, never
    around it: the heartbeat renews on its own connection, so holding this
    row lock while it was still beating would make it block on this
    transaction for no reason.
    """
    if worker_id is not None and settings is not None:
        with LeaseHeartbeat(
            settings,
            job_id=job.id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            interval_seconds=heartbeat_seconds,
        ) as beat:
            units = list(handler.plan(ctx))
        if beat.ownership_lost:
            raise OwnershipLostError(
                "This worker lost the job's lease while planning it.",
                technical_detail=(
                    f"job_id={job.id} worker_id={worker_id} beats={beat.beats} errors={beat.errors}"
                ),
                remediation=("Another worker owns this job now. Stand down and let it plan."),
            )
    else:
        units = list(handler.plan(ctx))

    # The proof and the write are one serialization unit: assert_owner holds
    # the row lock until the commit below lands the plan.
    if worker_id is not None:
        assert_owner(session, job.id, worker_id, action="commit plan")
    plan_units(session, job, units)
    session.commit()
    return units


def _owns_live_lease(settings: Any, job_id: uuid.UUID, worker_id: uuid.UUID) -> bool:
    """Non-locking probe: is this worker the owner of a still-live lease?

    Point-in-time by design. It exists to catch a stall immediately before
    the effect, not to serialise anything -- the serialisation happens in
    ``_authorize_effect``, under the row lock. Taking a lock here would hold
    it for the entire effect and block every other writer, the API's pause
    and cancel flags included.

    **It runs on its own short-lived session, exactly as LeaseHeartbeat
    does**, and that is not a stylistic choice. Using the executing session
    would leave a transaction open for the whole duration of the effect,
    which nothing else in the unit loop does -- ``record_event`` only stages
    the STEP_STARTED row, it does not flush. A transaction held open across
    a multi-hour render pins ``xmin`` and stops vacuum from reclaiming
    anything, and the first statement inside it would autoflush that pending
    event, whose foreign key takes a FOR KEY SHARE lock on the job row.
    ``reap_expired_leases`` selects FOR UPDATE SKIP LOCKED, so it would
    silently skip the job -- and a worker that hung with its connection
    still alive would hold the job hostage from the reaper indefinitely,
    defeating the recovery this system exists to provide.
    """
    from continuum_db.session import session_scope

    with session_scope(settings) as probe:
        return (
            probe.execute(
                select(Job.id).where(
                    Job.id == job_id,
                    Job.status == JobStatus.RUNNING,
                    Job.lease_owner == worker_id,
                    Job.lease_expires_at > func.now(),
                )
            ).scalar_one_or_none()
            is not None
        )


def _lease_is_alive(session: Session, job_id: uuid.UUID) -> bool:
    """Whether this job's lease has not yet expired, by the DATABASE clock.

    ``now()`` is evaluated by PostgreSQL, never by the worker. ADR-0002
    section 5 is explicit that clock skew between machines must not be able
    to expire a live lease, and the same reasoning applies in reverse: a
    worker with a fast clock must not be able to talk itself out of a lease
    it still holds, nor a worker with a slow one into a lease it has lost.
    """
    return (
        session.execute(
            select(Job.id).where(Job.id == job_id, Job.lease_expires_at > func.now())
        ).scalar_one_or_none()
        is not None
    )


def _authorize_effect(
    session: Session, job_id: uuid.UUID, worker_id: uuid.UUID, lease_seconds: int
) -> bool:
    """Renew this worker's lease under the row lock, before any effect runs.

    **The defect this closes (cold audit H-6).** The pre-unit proof used to
    be the last word before ``handler.execute_unit()``, and the row lock was
    released by the step-start commit. The ``LeaseHeartbeat`` that keeps the
    lease alive during the effect is only entered *after* that commit, and
    its first beat is a whole interval later. Between those two points the
    worker held no lock and no fresh lease, so the reaper could legitimately
    reclaim and a second worker could claim -- and the audit proved the first
    worker then began the effect anyway, with the job durably owned by
    someone else. The completion write was correctly refused, so nothing was
    corrupted, but two workers executed the same unit. Effect idempotency
    (ADR-0002 section 2) makes that survivable; it does not make it correct.

    **Why a renewal rather than another check.** A check answers "did I own
    this a moment ago". A renewal answers "am I the executor for the next
    ``lease_seconds``", which is the question the effect actually depends on.
    Because it runs inside the transaction that still holds the row lock, no
    reaper can interleave: ``reap_expired_leases`` takes ``FOR UPDATE SKIP
    LOCKED`` and skips this row entirely while the lock is held.

    **The expired-but-unreaped decision, made explicit.** ``renew_lease``
    deliberately carries no expiry predicate: a worker that is still the
    durable owner may renew a lapsed lease, because in this design *reaping*
    transfers ownership, not the clock. That is preserved exactly, and it is
    what lets the heartbeat keep a genuinely-running unit alive across a
    momentary lapse. The stricter rule is applied one level up, in
    ``_stop_requested``: **starting a new effect** on a lapsed lease is
    refused, because at that point the worker has no evidence it is still
    the executor and the reaper is entitled to act at any moment. Keeping a
    running unit alive and beginning a new one are different questions, and
    they get different answers.

    Returns ``False`` when the renewal is refused -- the job is no longer
    ``RUNNING``, or is owned by another worker -- in which case the caller
    must stand down without executing anything.
    """
    if not renew_lease(session, job_id, lease_seconds, worker_id=worker_id):
        return False
    # Belt and braces: prove from durable state, under the same lock, that
    # the row this worker is about to act on is RUNNING, owned by it, and
    # carries a lease the database agrees is still in the future.
    return (
        session.execute(
            select(Job.id).where(
                Job.id == job_id,
                Job.status == JobStatus.RUNNING,
                Job.lease_owner == worker_id,
                Job.lease_expires_at > func.now(),
            )
        ).scalar_one_or_none()
        is not None
    )


def _still_owns(session: Session, job_id: uuid.UUID, worker_id: uuid.UUID) -> bool:
    """Durable ownership check for paths where raising is the wrong shape."""
    locked = lock_job_row(session, job_id)
    return (
        locked is not None
        and locked.status is JobStatus.RUNNING
        and locked.lease_owner == worker_id
    )


def record_ownership_loss(session: Session, job_id: uuid.UUID, worker_id: uuid.UUID | None) -> None:
    """Audit that this worker stood down. Deliberately writes no status."""
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

    **Takes the job row lock and deliberately does not release it.** The
    caller continues under that lock to write the step-start record, which is
    what makes "prove ownership, then mutate the step" a single serialization
    unit (re-audit H-4).

    This previously used an unlocked ``session.refresh()``. Re-reading is not
    the same as holding: the refresh proved ownership at an instant and then
    let go, leaving three statements of window before the step-start commit
    in which the lease could be reclaimed. A stale worker would then stamp
    ``status``, ``started_at`` and ``attempt`` on the rightful owner's step
    row -- and ``step.attempt`` is read by handlers to decide retries, so the
    corruption changed the new owner's behaviour rather than merely being
    untidy.

    Landing a stop (``_land_stop``) also runs under this same lock, since
    ``transition`` re-locking a row this transaction already holds is a
    no-op.
    """
    locked = lock_job_row(session, job.id)
    if locked is None:
        # The row is gone. There is nothing left to own, and nothing this
        # worker may write.
        return StopReason.OWNERSHIP_LOST
    if worker_id is not None and (
        locked.lease_owner != worker_id or locked.status is not JobStatus.RUNNING
    ):
        return StopReason.OWNERSHIP_LOST
    if worker_id is not None and not _lease_is_alive(session, job.id):
        # H-6: being the recorded owner is not the same as holding a live
        # lease. A worker stalled past ``worker_lease_seconds`` -- a GC
        # pause, a swapped-out process, a suspended VM -- is still named as
        # the owner, but every other actor in the system is entitled to
        # treat that job as abandoned. Starting a NEW unit on that evidence
        # is not defensible, so this stands down and lets the reaper hand
        # the job to someone who can actually run it.
        #
        # The comparison is made by PostgreSQL against ``now()``, never
        # against worker local time (ADR-0002 section 5): clock skew between
        # machines must not be able to decide who owns a job.
        return StopReason.OWNERSHIP_LOST
    if locked.cancel_requested:
        return StopReason.CANCELLED
    if locked.pause_requested:
        return StopReason.PAUSED
    if worker_id is not None and worker_should_drain(session, worker_id):
        # A plain SELECT on the worker table: it takes no lock, so holding
        # the job row lock across it cannot invert with the worker loop,
        # which writes the worker row before locking any job.
        return StopReason.DRAINED
    return None


def _land_stop(session: Session, job: Job, reason: StopReason, worker_id: uuid.UUID | None) -> None:
    """Move a stopped job to its resting state, leaving it resumable.

    Every transition here is a worker-owned RUNNING transition, so each
    carries ``require_owner``. Only the FIRST needs it strictly -- once it
    succeeds the job has left RUNNING and this worker is the only actor --
    but the row lock taken inside ``transition`` is held for the whole
    caller transaction, so the follow-up transitions are already protected
    and are written without the owner requirement they could no longer
    satisfy.
    """
    if reason is StopReason.CANCELLED:
        if job.status is JobStatus.RUNNING:
            transition(
                session,
                job,
                JobStatus.CANCELLING,
                worker_id=worker_id,
                require_owner=worker_id,
            )
        transition(session, job, JobStatus.CANCELLED, worker_id=worker_id)
        return

    # Pause and drain both leave the job resumable from its completed units.
    if job.status is JobStatus.RUNNING:
        transition(
            session,
            job,
            JobStatus.PAUSING,
            worker_id=worker_id,
            require_owner=worker_id,
        )
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
