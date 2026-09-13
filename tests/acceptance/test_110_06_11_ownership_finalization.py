"""Ownership after a unit: final-audit hypotheses H-1, H-2 and H-3.

The lease/reaper remediation (second audit C-1) made the *reaper* safe
against a live worker. These tests attack the other direction: a worker
that has **already lost** its job and keeps going.

* **H-1** - worker A's unit returns, its heartbeat stops, and before A has
  finalized, the job is reaped and claimed by worker B. A must not record
  progress, checkpoint, extend B's lease, or mark B's job SUCCEEDED.
* **H-2** - A's handler raises after A has lost the job. A must not write
  STEP_FAILED, retry bookkeeping or a failure status onto B's job.
* **H-3** - a transition made from a stale in-memory job must be refused by
  the database, not merely avoided by careful callers. Sessions here use
  ``expire_on_commit=False`` exactly like production, so a worker's view of
  the row survives its own commits and can go stale without it noticing.

**How the interleavings are forced.** No sleeps. Each takeover runs at a
precise point in worker A's execution:

* immediately after A's :class:`LeaseHeartbeat` has stopped (a subclass
  swapped into ``continuum_jobs.execution`` runs the takeover in ``__exit__``,
  after the heartbeat thread has been joined);
* immediately after a specific commit of A's session (a SQLAlchemy
  ``after_commit`` listener);
* inside the handler, waiting on the heartbeat's own ownership-lost event.

The takeover itself is ordinary production code on a separate session:
expire the lease, ``reap_expired_leases``, ``claim_next_job`` for B.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pytest
from continuum_config import Settings
from continuum_core import ContinuumError, JobStatus
from continuum_db.enums import JobEventType, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobEvent, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    LeaseHeartbeat,
    UnitOutcome,
    UnitSpec,
    apply_pending_requests,
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
    request_cancel,
    request_pause,
    resume_job,
    transition,
)
from continuum_jobs import execution as execution_module
from continuum_jobs.execution import JobContext, StopReason
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.requires_db

PROBE_TYPE = "test.ownership_probe"
#: Long enough that A's heartbeat never beats during a test unless the test
#: wants it to. Ordering never depends on this: every takeover is triggered
#: by a hook, and the heartbeat's first beat is minutes away.
IDLE_HEARTBEAT_SECONDS = 3600.0


# ---------------------------------------------------------------------------
# Fixtures and scaffolding
# ---------------------------------------------------------------------------


class ProbeHandler:
    """``units`` trivial units, each with a checkpoint, and an optional hook
    that runs inside ``execute_unit``."""

    job_type: ClassVar[str] = PROBE_TYPE

    def __init__(
        self,
        units: int = 1,
        during_unit: Callable[[JobContext, UnitSpec], None] | None = None,
    ) -> None:
        self.units = units
        self.during_unit = during_unit
        self.executed: list[str] = []

    def plan(self, ctx: JobContext) -> Sequence[UnitSpec]:
        return [UnitSpec(unit_key=f"unit-{i}", ordinal=i) for i in range(self.units)]

    def execute_unit(self, ctx: JobContext, unit: UnitSpec) -> UnitOutcome:
        self.executed.append(unit.unit_key)
        if self.during_unit is not None:
            self.during_unit(ctx, unit)
        return UnitOutcome(result={"unit": unit.unit_key}, checkpoint={"after": unit.unit_key})


@dataclass
class Snapshot:
    """Everything a stale worker could touch, as committed by the takeover."""

    owner: uuid.UUID | None
    status: JobStatus
    lease_expires_at: dt.datetime | None
    attempt: int
    units_done: int
    current_step: int
    elapsed_active_ms: int
    last_error: Any
    error_history: Any
    steps: dict[str, tuple[StepStatus, int, Any]]
    checkpoints: int
    event_ids: set[uuid.UUID] = field(default_factory=set)


def _snapshot(session: Session, job_id: uuid.UUID) -> Snapshot:
    job = session.execute(select(Job).where(Job.id == job_id)).scalar_one()
    steps = {
        s.unit_key: (s.status, s.attempt, s.last_error)
        for s in session.execute(select(JobStep).where(JobStep.job_id == job_id)).scalars()
    }
    checkpoints = session.execute(
        select(func.count()).select_from(JobCheckpoint).where(JobCheckpoint.job_id == job_id)
    ).scalar_one()
    events = set(session.execute(select(JobEvent.id).where(JobEvent.job_id == job_id)).scalars())
    return Snapshot(
        owner=job.lease_owner,
        status=job.status,
        lease_expires_at=job.lease_expires_at,
        attempt=job.attempt,
        units_done=job.units_done,
        current_step=job.current_step,
        elapsed_active_ms=job.elapsed_active_ms,
        last_error=job.last_error,
        error_history=job.error_history,
        steps=steps,
        checkpoints=int(checkpoints),
        event_ids=events,
    )


def _take_over(settings: Settings, job_id: uuid.UUID, new_owner: uuid.UUID) -> Snapshot:
    """Reap worker A's job and let worker B claim it, committed.

    The lock timeout only converts a would-be hang into a clear failure if a
    future change made A hold the row at a point where it should not.
    """
    with session_scope(settings) as session:
        session.execute(text("SET LOCAL lock_timeout = '10s'"))
        job = session.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
        assert job.status is JobStatus.RUNNING, "nothing to take over"
        job.lease_expires_at = session.execute(
            select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 30))
        ).scalar_one()
        session.flush()
        assert job_id in reap_expired_leases(session)
        claimed = claim_next_job(
            session, worker_id=new_owner, resource_classes=["cpu"], lease_seconds=300
        )
        assert claimed is not None and claimed.id == job_id
        session.flush()
        taken = _snapshot(session, job_id)
    assert taken.owner == new_owner
    return taken


def _assert_untouched_since(
    settings: Settings, job_id: uuid.UUID, taken: Snapshot, stale_worker: uuid.UUID
) -> None:
    """The job is exactly as worker B's takeover committed it.

    The only thing the stale worker may add is its own stand-down record.
    """
    with session_scope(settings) as session:
        now = _snapshot(session, job_id)
        new_events = (
            session.execute(
                select(JobEvent).where(
                    JobEvent.job_id == job_id, JobEvent.id.not_in(taken.event_ids)
                )
            )
            .scalars()
            .all()
        )
    assert now.status is JobStatus.RUNNING, f"stale worker moved B's job to {now.status}"
    assert now.owner == taken.owner, "stale worker changed the lease owner"
    assert now.lease_expires_at == taken.lease_expires_at, "stale worker moved B's lease"
    assert (now.units_done, now.current_step, now.elapsed_active_ms) == (
        taken.units_done,
        taken.current_step,
        taken.elapsed_active_ms,
    ), "stale worker wrote progress onto B's job"
    assert now.checkpoints == taken.checkpoints, "stale worker checkpointed B's job"
    assert now.steps == taken.steps, "stale worker changed step state"
    assert (now.attempt, now.last_error, now.error_history) == (
        taken.attempt,
        taken.last_error,
        taken.error_history,
    ), "stale worker wrote failure/retry bookkeeping"
    unexpected = [
        (e.event_type.value, e.to_status.value if e.to_status else None)
        for e in new_events
        if not (e.event_type is JobEventType.LEASE_EXPIRED and e.worker_id == stale_worker)
    ]
    assert unexpected == [], f"stale worker recorded events on B's job: {unexpected}"


@pytest.fixture
def workers(clean_jobs: Session) -> tuple[uuid.UUID, uuid.UUID]:
    a = register_worker(clean_jobs)
    b = register_worker(clean_jobs)
    clean_jobs.commit()
    return a.id, b.id


def _claimed_by(session: Session, worker_id: uuid.UUID, *, units: int) -> uuid.UUID:
    job, created = enqueue(session, PROBE_TYPE, payload={"units": units, "n": str(uuid.uuid4())})
    assert created
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker_id, resource_classes=["cpu"], lease_seconds=900
    )
    session.commit()
    assert claimed is not None and claimed.id == job.id
    return job.id


def _heartbeat_class(on_exit: Callable[[LeaseHeartbeat], None] | None = None):
    """A LeaseHeartbeat that records its instances and runs ``on_exit`` after
    its thread has been stopped and joined."""
    created: list[LeaseHeartbeat] = []

    class ObservedHeartbeat(LeaseHeartbeat):
        def __enter__(self) -> LeaseHeartbeat:
            created.append(self)
            return super().__enter__()

        def __exit__(self, *exc: object) -> None:
            super().__exit__(*exc)
            if on_exit is not None:
                on_exit(self)

    return ObservedHeartbeat, created


def _run_as(
    settings: Settings,
    job_id: uuid.UUID,
    worker_id: uuid.UUID,
    handler: ProbeHandler,
    *,
    heartbeat_seconds: float = IDLE_HEARTBEAT_SECONDS,
    lease_seconds: int = 900,
    on_session: Callable[[Session], None] | None = None,
) -> StopReason:
    with session_scope(settings) as session:
        if on_session is not None:
            on_session(session)
        job = session.get(Job, job_id)
        assert job is not None
        return execute_job(
            session,
            job,
            handler,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            settings=settings,
            heartbeat_seconds=heartbeat_seconds,
        )


def _after_first_commit_once_armed(session: Session, armed: threading.Event, action) -> None:
    fired = threading.Event()

    def after_commit(_session: Session) -> None:
        if armed.is_set() and not fired.is_set():
            fired.set()
            action()

    event.listen(session, "after_commit", after_commit)


# ---------------------------------------------------------------------------
# H-1: ownership lost after the unit returns
# ---------------------------------------------------------------------------


class TestOwnershipLostAfterTheUnit:
    def test_no_progress_or_checkpoint_after_losing_the_job_before_the_completion_commit(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        """A's heartbeat has stopped; B takes the job before A commits the
        unit. A must stand down with nothing written."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        taken: list[Snapshot] = []

        def take_over_once(_beat: LeaseHeartbeat) -> None:
            if not taken:
                taken.append(_take_over(db_settings, job_id, b))

        heartbeat_cls, _ = _heartbeat_class(on_exit=take_over_once)
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)

        reason = _run_as(db_settings, job_id, a, ProbeHandler(units=1))

        assert taken, "the takeover never ran; the interleaving was not exercised"
        _assert_untouched_since(db_settings, job_id, taken[0], stale_worker=a)
        assert reason is StopReason.OWNERSHIP_LOST

    def test_final_success_is_not_written_after_losing_the_job(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        """A commits the last unit legitimately, then B takes the job before
        A's final transition. A must not mark B's job SUCCEEDED."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        armed = threading.Event()
        taken: list[Snapshot] = []

        heartbeat_cls, _ = _heartbeat_class(on_exit=lambda _beat: armed.set())
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)

        def watch(session: Session) -> None:
            _after_first_commit_once_armed(
                session, armed, lambda: taken.append(_take_over(db_settings, job_id, b))
            )

        reason = _run_as(db_settings, job_id, a, ProbeHandler(units=1), on_session=watch)

        assert taken, "the takeover never ran; the interleaving was not exercised"
        assert taken[0].units_done == 1, "the takeover should follow A's unit commit"
        _assert_untouched_since(db_settings, job_id, taken[0], stale_worker=a)
        assert reason is StopReason.OWNERSHIP_LOST

    def test_a_stale_worker_cannot_extend_the_new_owners_lease(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        """Between units: B owns the job after A's first unit commit. A must
        not renew (or shorten) B's lease on its way to noticing."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=2)
        armed = threading.Event()
        taken: list[Snapshot] = []

        heartbeat_cls, _ = _heartbeat_class(on_exit=lambda _beat: armed.set())
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)

        def watch(session: Session) -> None:
            _after_first_commit_once_armed(
                session, armed, lambda: taken.append(_take_over(db_settings, job_id, b))
            )

        handler = ProbeHandler(units=2)
        reason = _run_as(db_settings, job_id, a, handler, on_session=watch)

        assert taken, "the takeover never ran; the interleaving was not exercised"
        _assert_untouched_since(db_settings, job_id, taken[0], stale_worker=a)
        assert reason is StopReason.OWNERSHIP_LOST
        assert handler.executed == ["unit-0"], "A must not start another unit"

    def test_reaped_work_is_completed_by_the_new_owner(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        """Standing down must leave the job fully recoverable by B."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=2)
        taken: list[Snapshot] = []

        def take_over_once(_beat: LeaseHeartbeat) -> None:
            if not taken:
                taken.append(_take_over(db_settings, job_id, b))

        heartbeat_cls, _ = _heartbeat_class(on_exit=take_over_once)
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)
        stale = _run_as(db_settings, job_id, a, ProbeHandler(units=2))
        assert stale is StopReason.OWNERSHIP_LOST
        monkeypatch.undo()

        recovered = ProbeHandler(units=2)
        reason = _run_as(db_settings, job_id, b, recovered, heartbeat_seconds=0.2, lease_seconds=30)

        assert reason is StopReason.COMPLETED
        assert recovered.executed == ["unit-0", "unit-1"]
        with session_scope(db_settings) as session:
            done = _snapshot(session, job_id)
        assert done.status is JobStatus.SUCCEEDED
        assert done.owner is None
        assert done.units_done == 2
        assert done.checkpoints == 2
        assert all(status is StepStatus.SUCCEEDED for status, _, _ in done.steps.values())


# ---------------------------------------------------------------------------
# H-2: the handler raises after ownership was lost
# ---------------------------------------------------------------------------


class TestHandlerFailureAfterOwnershipLoss:
    def test_failure_after_the_heartbeat_saw_the_loss_writes_nothing(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        heartbeat_cls, beats = _heartbeat_class()
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)
        taken: list[Snapshot] = []

        def lose_then_fail(_ctx: JobContext, _unit: UnitSpec) -> None:
            taken.append(_take_over(db_settings, job_id, b))
            # Wait on the heartbeat's own signal, not on time: its next beat
            # is refused because B owns the row.
            observed = beats[0]._ownership_lost.wait(timeout=60)
            assert observed, "the heartbeat never observed the loss"
            raise RuntimeError("the unit failed after its worker lost the job")

        reason = _run_as(
            db_settings,
            job_id,
            a,
            ProbeHandler(units=1, during_unit=lose_then_fail),
            heartbeat_seconds=0.1,
            lease_seconds=30,
        )

        assert taken
        _assert_untouched_since(db_settings, job_id, taken[0], stale_worker=a)
        assert reason is StopReason.OWNERSHIP_LOST

    def test_failure_after_an_unnoticed_loss_writes_nothing(
        self, clean_jobs, workers, db_settings, monkeypatch
    ) -> None:
        """The heartbeat has not noticed yet; the database still decides."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        heartbeat_cls, _ = _heartbeat_class()
        monkeypatch.setattr(execution_module, "LeaseHeartbeat", heartbeat_cls)
        taken: list[Snapshot] = []

        def lose_then_fail(_ctx: JobContext, _unit: UnitSpec) -> None:
            taken.append(_take_over(db_settings, job_id, b))
            raise RuntimeError("the unit failed after its worker lost the job")

        reason = _run_as(db_settings, job_id, a, ProbeHandler(units=1, during_unit=lose_then_fail))

        assert taken
        _assert_untouched_since(db_settings, job_id, taken[0], stale_worker=a)
        assert reason is StopReason.OWNERSHIP_LOST


# ---------------------------------------------------------------------------
# H-3: stale in-memory state cannot overwrite newer committed state
# ---------------------------------------------------------------------------


class TestStaleStateIsRefusedByTheDatabase:
    def test_stale_worker_transition_cannot_overwrite_a_newer_owner(
        self, clean_jobs, workers, db_settings
    ) -> None:
        """A loads its RUNNING job; B takes it over; A transitions from its
        stale object. The write must be refused, not applied."""
        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)

        stale = Session(bind=clean_jobs.get_bind(), expire_on_commit=False)
        try:
            mine = stale.get(Job, job_id)
            assert mine is not None and mine.lease_owner == a
            stale.commit()  # a worker's view survives its own commits

            taken = _take_over(db_settings, job_id, b)

            with pytest.raises(ContinuumError):
                transition(stale, mine, JobStatus.SUCCEEDED, worker_id=a)
                stale.commit()
        finally:
            stale.rollback()
            stale.close()

        _assert_untouched_since(db_settings, job_id, taken, stale_worker=a)

    def test_stale_resume_cannot_reopen_a_cancelled_job(self, clean_jobs, db_settings) -> None:
        """The API resumes from a PAUSED view after a worker cancelled the job.
        A terminal CANCELLED must not become QUEUED again."""
        session = clean_jobs
        job, _ = enqueue(session, PROBE_TYPE, payload={"n": str(uuid.uuid4())})
        session.commit()
        request_pause(session, job)
        apply_pending_requests(session)
        session.commit()
        assert job.status is JobStatus.PAUSED

        api = Session(bind=session.get_bind(), expire_on_commit=False)
        try:
            viewed = api.get(Job, job.id)
            assert viewed is not None and viewed.status is JobStatus.PAUSED
            api.commit()

            with session_scope(db_settings) as worker:
                live = worker.get(Job, job.id)
                assert live is not None
                request_cancel(worker, live)
                apply_pending_requests(worker)

            with pytest.raises(ContinuumError):
                resume_job(api, viewed)
                api.commit()
        finally:
            api.rollback()
            api.close()

        with session_scope(db_settings) as check:
            final = check.get(Job, job.id)
            assert final is not None
            assert final.status is JobStatus.CANCELLED, f"a cancelled job became {final.status}"

    def test_worker_block_path_cannot_overwrite_a_newer_owner(
        self, clean_jobs, workers, db_settings
    ) -> None:
        """The standalone worker parks a job BLOCKED when the handler reports
        a missing capability. If the job was taken over first, it must not."""
        from continuum_jobs import registry
        from continuum_worker.handlers.synthetic import SyntheticBlockedError
        from continuum_worker.main import Worker

        _a, b = workers
        taken: list[Snapshot] = []

        class BlockedAfterLoss(ProbeHandler):
            job_type: ClassVar[str] = "test.ownership_blocked_probe"

        def lose_then_block(ctx: JobContext, _unit: UnitSpec) -> None:
            taken.append(_take_over(db_settings, ctx.job_id, b))
            raise SyntheticBlockedError(
                "No provider can serve this capability.", blocked_reason="MISSING_PROVIDER"
            )

        if "test.ownership_blocked_probe" not in registry.known_types():
            registry.register(BlockedAfterLoss(units=1))
        handler = registry.get("test.ownership_blocked_probe")
        assert isinstance(handler, ProbeHandler)
        handler.during_unit = lose_then_block

        session = clean_jobs
        job, _ = enqueue(session, "test.ownership_blocked_probe", payload={"n": str(uuid.uuid4())})
        session.commit()

        worker = Worker(db_settings)
        worker.register()
        assert worker.run_once() is True

        assert taken, "the takeover never ran; the interleaving was not exercised"
        assert worker.worker_id is not None
        _assert_untouched_since(db_settings, job.id, taken[0], stale_worker=worker.worker_id)


# ---------------------------------------------------------------------------
# Preserved behaviour
# ---------------------------------------------------------------------------


class TestLiveWorkerStillCompletes:
    def test_a_live_worker_with_a_beating_heartbeat_completes_normally(
        self, clean_jobs, workers, db_settings
    ) -> None:
        a, _b = workers
        job_id = _claimed_by(clean_jobs, a, units=3)
        handler = ProbeHandler(units=3)

        reason = _run_as(db_settings, job_id, a, handler, heartbeat_seconds=0.1, lease_seconds=30)

        assert reason is StopReason.COMPLETED
        assert handler.executed == ["unit-0", "unit-1", "unit-2"]
        with session_scope(db_settings) as session:
            done = _snapshot(session, job_id)
            renewals = session.execute(
                select(func.count())
                .select_from(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.event_type == JobEventType.LEASE_RENEWED)
            ).scalar_one()
        assert done.status is JobStatus.SUCCEEDED
        assert done.owner is None and done.lease_expires_at is None
        assert done.units_done == 3 and done.current_step == 3
        assert done.checkpoints == 3
        assert all(status is StepStatus.SUCCEEDED for status, _, _ in done.steps.values())
        assert renewals >= 3, "the lease must still be renewed as units complete"


# ---------------------------------------------------------------------------
# The guard's contract
# ---------------------------------------------------------------------------


class TestOwnershipGuardContract:
    def test_renew_lease_has_no_unowned_form(self, clean_jobs, workers) -> None:
        from continuum_jobs import renew_lease

        a, _b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        with pytest.raises(TypeError):
            renew_lease(clean_jobs, job_id, 300)  # type: ignore[call-arg]

    def test_owner_is_checked_even_from_a_fresh_view(
        self, clean_jobs, workers, db_settings
    ) -> None:
        """Freshness alone is not ownership: a worker that reloads the row
        after losing it sees B's lease, and must still be refused."""
        from continuum_jobs import JobOwnershipLostError

        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        taken = _take_over(db_settings, job_id, b)

        with session_scope(db_settings) as session:
            fresh = session.get(Job, job_id)
            assert fresh is not None and fresh.lease_owner == b
            with pytest.raises(JobOwnershipLostError):
                transition(session, fresh, JobStatus.SUCCEEDED, worker_id=a, owner=a)
            session.rollback()

        _assert_untouched_since(db_settings, job_id, taken, stale_worker=a)

    def test_fail_job_refuses_before_touching_retry_bookkeeping(
        self, clean_jobs, workers, db_settings
    ) -> None:
        from continuum_core import ErrorCategory, StructuredError
        from continuum_jobs import JobOwnershipLostError, fail_job

        a, b = workers
        job_id = _claimed_by(clean_jobs, a, units=1)
        taken = _take_over(db_settings, job_id, b)
        error = StructuredError(
            code="test.failure",
            category=ErrorCategory.RETRYABLE_TRANSIENT,
            user_message="failed",
        )

        with session_scope(db_settings) as session:
            fresh = session.get(Job, job_id)
            assert fresh is not None
            with pytest.raises(JobOwnershipLostError):
                fail_job(session, fresh, error, worker_id=a, owner=a)
            assert fresh.attempt == taken.attempt, "bookkeeping was touched before the refusal"
            session.rollback()

        _assert_untouched_since(db_settings, job_id, taken, stale_worker=a)
