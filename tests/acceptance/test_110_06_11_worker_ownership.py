"""Worker-ownership regression suite — final audit H-1, H-2, H-3.

**The invariant.** No worker may mutate durable job coordination, progress or
final status after it no longer owns the current RUNNING lease. Ownership
validation and the mutation are one PostgreSQL serialization unit.

**The three defects this pins down.**

* **H-1** — the last-unit sequence had an ownership-free interval after the
  heartbeat context exited. A stale worker could commit ``JobStep.SUCCEEDED``,
  progress and a checkpoint, renew *another worker's* lease, and transition
  their ``RUNNING`` job to ``SUCCEEDED``.
* **H-2** — the exception path never consulted the heartbeat. A handler that
  raised after ownership had provably transferred still wrote ``STEP_FAILED``,
  error history, attempts and failure status onto the new owner's job.
* **H-3** — ``transition()`` validated the status of an in-memory ORM object
  that could be arbitrarily stale, then wrote without locking or re-reading.

**Ported, not copied.** Codex's audit artifacts cannot run verbatim against
the remediation, for two reasons that are themselves the fix:

1. the H-1 artifact synchronises on the post-unit ``renew_lease`` being called
   *without* ``worker_id`` — the very defect that was removed, so the hook can
   never fire again;
2. the H-3 artifact expects ``transition()`` to decline silently, whereas it
   now raises :class:`OwnershipLostError`. Raising is the stronger contract:
   a silent no-op would let a stale worker believe it had finalised the job.

Each test below therefore asserts the same invariant through the corrected
interface. Synchronisation is by threading primitives and real ownership
transfer, never by sleeping on a guess.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from continuum_config import Settings
from continuum_core import JobStatus, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    OwnershipLostError,
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
    renew_lease,
    transition,
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec
from sqlalchemy import func, select, update

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Handlers and helpers
# ---------------------------------------------------------------------------


class _SuccessfulHandler:
    """One unit that succeeds immediately."""

    job_type = "ownership.success"

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, _ctx, _unit):
        return UnitOutcome(result={"landed": True}, checkpoint={"at": "only"})


class _GatedHandler:
    """Signals when it is inside the unit, then waits to be released.

    Lets a test transfer ownership at a precise point *while the unit is
    executing*, which is what makes the interleaving deterministic.
    """

    job_type = "ownership.gated"

    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self.entered = entered
        self.release = release

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, _ctx, _unit):
        self.entered.set()
        assert self.release.wait(30)
        return UnitOutcome(result={"landed": True}, checkpoint={"at": "only"})


class _GatedFailingHandler(_GatedHandler):
    """Same gate, but raises once released."""

    job_type = "ownership.gated_failure"

    def execute_unit(self, _ctx, _unit):
        self.entered.set()
        assert self.release.wait(30)
        raise RuntimeError("deterministic ownership-suite failure")


def _prepare(session, job_type: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One QUEUED job claimed by worker A, plus an idle worker B."""
    _job, _ = enqueue(session, job_type, payload={"case": str(uuid.uuid4())})
    worker_a = register_worker(session)
    worker_b = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker_a.id, resource_classes=["cpu"], lease_seconds=30
    )
    session.commit()
    assert claimed is not None
    return claimed.id, worker_a.id, worker_b.id


def _steal(settings: Settings, job_id: uuid.UUID, worker_b: uuid.UUID) -> None:
    """Transfer ownership to B through the real reaper and claim paths.

    Deliberately not a hand-written UPDATE: the point is that ownership moves
    exactly the way it moves in production.
    """
    with session_scope(settings) as session:
        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                lease_expires_at=session.execute(
                    select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 60))
                ).scalar_one()
            )
        )
    with session_scope(settings) as session:
        assert job_id in reap_expired_leases(session)
    with session_scope(settings) as session:
        claimed = claim_next_job(
            session, worker_id=worker_b, resource_classes=["cpu"], lease_seconds=300
        )
        assert claimed is not None and claimed.id == job_id


def _observe(settings: Settings, job_id: uuid.UUID) -> tuple[JobStatus, uuid.UUID | None]:
    with session_scope(settings) as session:
        row = session.execute(select(Job).where(Job.id == job_id)).scalar_one()
        return row.status, row.lease_owner


def _run_in_thread(settings: Settings, job_id: uuid.UUID, worker_id, handler, **kwargs):
    outcomes: list[StopReason] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            with session_scope(settings) as session:
                job = session.get(Job, job_id)
                assert job is not None
                outcomes.append(
                    execute_job(
                        session,
                        job,
                        handler,
                        worker_id=worker_id,
                        settings=settings,
                        **kwargs,
                    )
                )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcomes, errors


# ---------------------------------------------------------------------------
# H-1 — stale finalization
# ---------------------------------------------------------------------------


class TestStaleWorkerCannotFinalize:
    def test_stale_worker_cannot_finalize_after_reclaim(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 1. Ownership transfers while A is inside its
        final unit; A must stand down instead of writing SUCCEEDED."""
        job_id, worker_a, worker_b = _prepare(clean_jobs, _GatedHandler.job_type)
        entered, release = threading.Event(), threading.Event()

        thread, outcomes, errors = _run_in_thread(
            db_settings,
            job_id,
            worker_a,
            _GatedHandler(entered, release),
            lease_seconds=30,
            heartbeat_seconds=0.1,
        )
        assert entered.wait(30)

        _steal(db_settings, job_id, worker_b)
        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)

        release.set()
        thread.join(30)
        assert not thread.is_alive()
        assert errors == [], f"execute_job raised instead of standing down: {errors}"

        assert outcomes == [StopReason.OWNERSHIP_LOST]
        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)

    def test_stale_worker_writes_no_unit_completion_or_checkpoint(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 3. Not merely the final status: the step record,
        progress counters and checkpoint must all be withheld."""
        job_id, worker_a, worker_b = _prepare(clean_jobs, _GatedHandler.job_type)
        entered, release = threading.Event(), threading.Event()

        thread, outcomes, _errors = _run_in_thread(
            db_settings,
            job_id,
            worker_a,
            _GatedHandler(entered, release),
            lease_seconds=30,
            heartbeat_seconds=0.1,
        )
        assert entered.wait(30)
        _steal(db_settings, job_id, worker_b)
        release.set()
        thread.join(30)

        assert outcomes == [StopReason.OWNERSHIP_LOST]
        with session_scope(db_settings) as verify:
            step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
            assert step.status is not StepStatus.SUCCEEDED, (
                "a stale worker recorded the new owner's unit as completed"
            )
            checkpoints = verify.execute(
                select(func.count())
                .select_from(JobCheckpoint)
                .where(JobCheckpoint.job_id == job_id)
            ).scalar_one()
            assert checkpoints == 0, "a stale worker wrote a checkpoint"
            job = verify.get(Job, job_id)
            assert job is not None
            assert job.units_done == 0, "a stale worker advanced the new owner's progress"

    def test_stale_worker_cannot_renew_the_new_owners_lease(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 2, at the primitive."""
        job_id, worker_a, worker_b = _prepare(clean_jobs, _SuccessfulHandler.job_type)
        _steal(db_settings, job_id, worker_b)

        with session_scope(db_settings) as session:
            before = session.execute(
                select(Job.lease_expires_at).where(Job.id == job_id)
            ).scalar_one()
            assert renew_lease(session, job_id, 9999, worker_id=worker_a) is False

        with session_scope(db_settings) as verify:
            after = verify.execute(
                select(Job.lease_expires_at).where(Job.id == job_id)
            ).scalar_one()
        assert after == before, "a stale worker extended the new owner's lease"
        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)


# ---------------------------------------------------------------------------
# H-2 — exception after ownership loss
# ---------------------------------------------------------------------------


class TestExceptionAfterOwnershipLoss:
    def test_handler_exception_cannot_fail_the_new_owners_job(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 4. Ownership loss dominates the exception: A's
        failure is A's private problem, not a defect in B's execution."""
        job_id, worker_a, worker_b = _prepare(clean_jobs, _GatedFailingHandler.job_type)
        entered, release = threading.Event(), threading.Event()

        thread, outcomes, errors = _run_in_thread(
            db_settings,
            job_id,
            worker_a,
            _GatedFailingHandler(entered, release),
            lease_seconds=30,
            heartbeat_seconds=0.1,
        )
        assert entered.wait(30)
        _steal(db_settings, job_id, worker_b)
        release.set()
        thread.join(30)
        assert not thread.is_alive()
        assert errors == [], f"execute_job raised instead of standing down: {errors}"

        assert outcomes == [StopReason.OWNERSHIP_LOST], (
            "a stale worker reported FAILED for a job it no longer owned"
        )
        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)

        with session_scope(db_settings) as verify:
            job = verify.get(Job, job_id)
            assert job is not None
            assert job.last_error is None, "a stale worker attached its error to B's job"
            assert job.error_history == [], "a stale worker polluted B's error history"
            step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
            assert step.status is not StepStatus.FAILED, (
                "a stale worker marked the new owner's unit as failed"
            )

    def test_a_legitimate_owner_still_records_its_failure(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Guard the guard: real failures must still be recorded when the
        worker genuinely owns the job. A fix that swallowed every exception
        would pass the test above and be useless."""
        job_id, worker_a, _worker_b = _prepare(clean_jobs, _GatedFailingHandler.job_type)
        entered, release = threading.Event(), threading.Event()

        thread, outcomes, _errors = _run_in_thread(
            db_settings,
            job_id,
            worker_a,
            _GatedFailingHandler(entered, release),
            lease_seconds=300,
            heartbeat_seconds=0.2,
        )
        assert entered.wait(30)
        release.set()
        thread.join(30)

        assert outcomes == [StopReason.FAILED]
        with session_scope(db_settings) as verify:
            job = verify.get(Job, job_id)
            assert job is not None
            assert job.status in (JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_FINAL)
            assert job.last_error is not None
            assert job.error_history


# ---------------------------------------------------------------------------
# H-3 — stale unlocked transition
# ---------------------------------------------------------------------------


class TestTransitionIsAtomic:
    def test_stale_orm_snapshot_cannot_overwrite_a_newer_owner(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 5.

        Codex's artifact expected a silent refusal; the remediation raises
        instead. Raising is the stronger contract -- a silent no-op would let
        a stale worker believe it had finalised the job. The invariant the
        artifact was protecting is asserted unchanged: B's row is untouched.
        """
        job_id, worker_a, worker_b = _prepare(clean_jobs, "ownership.transition")

        with session_scope(db_settings) as stale_session:
            stale = stale_session.get(Job, job_id)
            assert stale is not None and stale.lease_owner == worker_a

            _steal(db_settings, job_id, worker_b)

            with pytest.raises(OwnershipLostError):
                transition(stale_session, stale, JobStatus.SUCCEEDED, worker_id=worker_a)
            stale_session.rollback()

        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)

    def test_ownership_is_required_by_default_not_by_opt_in(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """The root-fix property. A caller that identifies as a worker while
        the row is RUNNING must prove ownership even without passing
        ``require_owner`` -- otherwise every call site is one forgotten
        keyword away from reintroducing H-3."""
        job_id, worker_a, worker_b = _prepare(clean_jobs, "ownership.default")
        _steal(db_settings, job_id, worker_b)

        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            for target in (JobStatus.SUCCEEDED, JobStatus.PAUSING, JobStatus.CANCELLING):
                with pytest.raises(OwnershipLostError):
                    transition(session, job, target, worker_id=worker_a)
                session.rollback()

        assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)

    def test_transition_reloads_rather_than_trusting_a_snapshot(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Validation must read durable state, not the caller's memory.

        The stale object still says RUNNING; the database says QUEUED. The
        state machine must judge the database.
        """
        job_id, worker_a, _worker_b = _prepare(clean_jobs, "ownership.reload")

        with session_scope(db_settings) as stale_session:
            stale = stale_session.get(Job, job_id)
            assert stale is not None and stale.status is JobStatus.RUNNING

            # Reap it elsewhere: durable status becomes QUEUED.
            with session_scope(db_settings) as other:
                other.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(
                        lease_expires_at=other.execute(
                            select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 60))
                        ).scalar_one()
                    )
                )
            with session_scope(db_settings) as other:
                assert job_id in reap_expired_leases(other)

            with pytest.raises(OwnershipLostError):
                transition(stale_session, stale, JobStatus.SUCCEEDED, worker_id=worker_a)
            stale_session.rollback()

        status, owner = _observe(db_settings, job_id)
        assert status is JobStatus.QUEUED
        assert owner is None


# ---------------------------------------------------------------------------
# Legitimate paths must keep working
# ---------------------------------------------------------------------------


class TestLegitimatePathsStillWork:
    def test_rightful_owner_completes_normally(self, clean_jobs, db_settings: Settings) -> None:
        """Required scenario 6."""
        job_id, worker_a, _b = _prepare(clean_jobs, _SuccessfulHandler.job_type)

        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            outcome = execute_job(
                session,
                job,
                _SuccessfulHandler(),
                worker_id=worker_a,
                settings=db_settings,
                lease_seconds=300,
                heartbeat_seconds=0.2,
            )

        assert outcome is StopReason.COMPLETED
        status, _owner = _observe(db_settings, job_id)
        assert status is JobStatus.SUCCEEDED
        with session_scope(db_settings) as verify:
            step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
            assert step.status is StepStatus.SUCCEEDED
            job = verify.get(Job, job_id)
            assert job is not None and job.units_done == 1

    def test_reaper_recovery_still_works(self, clean_jobs, db_settings: Settings) -> None:
        """Required scenario 7. The reaper is privileged recovery and must not
        be blocked by the ownership requirement it does not participate in."""
        job_id, _worker_a, _worker_b = _prepare(clean_jobs, _SuccessfulHandler.job_type)

        with session_scope(db_settings) as session:
            session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(
                    lease_expires_at=session.execute(
                        select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 60))
                    ).scalar_one()
                )
            )
        with session_scope(db_settings) as session:
            assert job_id in reap_expired_leases(session)

        status, owner = _observe(db_settings, job_id)
        assert status is JobStatus.QUEUED
        assert owner is None

    def test_pause_drain_and_cancel_landings_still_work(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """Required scenario 8. The owner-scoped transitions must not have
        made legitimate cooperative stops impossible."""
        from continuum_jobs import request_cancel, request_drain, request_pause, resume_job

        # Pause, applied by the worker path.
        job_id, worker_a, _b = _prepare(clean_jobs, _SuccessfulHandler.job_type)
        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            request_pause(session, job)
            job.pause_requested = True
            outcome = execute_job(
                session,
                job,
                _SuccessfulHandler(),
                worker_id=worker_a,
                settings=db_settings,
                lease_seconds=300,
                heartbeat_seconds=0.2,
            )
        assert outcome is StopReason.PAUSED
        assert _observe(db_settings, job_id)[0] is JobStatus.PAUSED

        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            resume_job(session, job)
        assert _observe(db_settings, job_id)[0] is JobStatus.QUEUED

        # Cancel.
        cancel_id, cancel_worker, _ = _prepare(clean_jobs, _SuccessfulHandler.job_type)
        with session_scope(db_settings) as session:
            job = session.get(Job, cancel_id)
            assert job is not None
            request_cancel(session, job)
            job.cancel_requested = True
            outcome = execute_job(
                session,
                job,
                _SuccessfulHandler(),
                worker_id=cancel_worker,
                settings=db_settings,
                lease_seconds=300,
                heartbeat_seconds=0.2,
            )
        assert outcome is StopReason.CANCELLED
        assert _observe(db_settings, cancel_id)[0] is JobStatus.CANCELLED

        # Drain requeues rather than cancelling.
        drain_id, drain_worker, _ = _prepare(clean_jobs, _SuccessfulHandler.job_type)
        with session_scope(db_settings) as session:
            request_drain(session, drain_worker)
        with session_scope(db_settings) as session:
            job = session.get(Job, drain_id)
            assert job is not None
            outcome = execute_job(
                session,
                job,
                _SuccessfulHandler(),
                worker_id=drain_worker,
                settings=db_settings,
                lease_seconds=300,
                heartbeat_seconds=0.2,
            )
        assert outcome is StopReason.DRAINED
        assert _observe(db_settings, drain_id)[0] is JobStatus.QUEUED
