"""Lease-clock and event-flush suite — final audit H-8 and H-9.

**The invariant.** A worker that no longer owns the current RUNNING lease must
not mutate durable state and must not continue acting as the executor of that
job. Ownership validation and mutation must be serialized through PostgreSQL.

Both defects here are about *when* and *where* that serialization is judged.

* **H-8 — the frozen clock.** ``now()`` is ``transaction_timestamp()``: it is
  fixed when the transaction begins and does not advance while that
  transaction waits on a row lock. ``_stop_requested`` blocks on exactly such
  a lock, so a lease that expired *during* the wait was still judged alive,
  and the worker committed ``JobStep.RUNNING``, ``started_at`` and an
  ``attempt`` increment on a dead lease. Worse, ``_authorize_effect`` then
  compared a deadline it had just written as ``now() + lease_seconds``
  against ``now()`` itself — true by construction, proving nothing. The fix
  is ``clock_timestamp()``, which is still the database clock (ADR-0002
  section 5 holds: the worker's local clock is never consulted) but advances.

* **H-9 — the pending event.** ``STEP_STARTED`` was staged after the
  step-start commit and left unflushed, so the handler received a session
  carrying a pending coordination write. The first query any handler made
  through ``ctx.session`` autoflushed it, and that INSERT's foreign key takes
  a ``FOR KEY SHARE`` lock on the job row for as long as the effect runs.
  ``reap_expired_leases`` selects ``FOR UPDATE SKIP LOCKED`` and therefore
  skipped the job entirely: a handler that hung with a live connection made
  its job unrecoverable for exactly as long as it hung. The fix commits the
  event with the authorized step start.

Both are tested against real PostgreSQL. Time is advanced deliberately with
``pg_sleep`` inside a *separate* session — the point is to move the database
wall clock past a deadline while another transaction is provably blocked, not
to wait and hope.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any, ClassVar

import pytest
from continuum_config import Settings
from continuum_core import JobStatus, StepStatus
from continuum_db.enums import JobEventType
from continuum_db.models import Job, JobEvent, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec, plan_units
from sqlalchemy import func, select, text

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


class _Counter:
    job_type: ClassVar[str] = "test.lease_clock"

    def __init__(self) -> None:
        self.effects = 0

    def plan(self, _ctx: Any) -> list[UnitSpec]:
        return [UnitSpec("only")]

    def execute_unit(self, _ctx: Any, _unit: UnitSpec) -> UnitOutcome:
        self.effects += 1
        return UnitOutcome(result={"landed": True})


class _QueryThenBlock:
    """Performs one harmless query through ``ctx.session``, then blocks.

    The query is the whole point: before the fix it autoflushed the pending
    ``STEP_STARTED`` event and took a foreign-key lock on the job row.
    """

    job_type: ClassVar[str] = "test.lease_clock_query"

    def __init__(self, queried: threading.Event, release: threading.Event) -> None:
        self.queried = queried
        self.release = release
        self.pending_at_effect_start: list[bool] = []

    def plan(self, _ctx: Any) -> list[UnitSpec]:
        return [UnitSpec("only")]

    def execute_unit(self, ctx: Any, _unit: UnitSpec) -> UnitOutcome:
        # Whether the executor handed us a session with unflushed work.
        self.pending_at_effect_start.append(
            bool(ctx.session.new or ctx.session.dirty or ctx.session.deleted)
        )
        ctx.session.execute(select(func.count()).select_from(JobStep)).scalar_one()
        self.queried.set()
        assert self.release.wait(60), "handler gate never released"
        return UnitOutcome(result={"landed": True})


def _prepare(session, job_type: str, *, lease_seconds: int = 1) -> tuple[uuid.UUID, uuid.UUID]:
    enqueue(session, job_type, payload={"case": str(uuid.uuid4())})
    worker = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=lease_seconds
    )
    session.commit()
    assert claimed is not None
    return claimed.id, worker.id


def _advance_database_clock(settings: Settings, seconds: float) -> None:
    """Move real database wall time forward, in its own session.

    ``pg_sleep`` here is not a race-control sleep. Another transaction is
    already provably blocked on a row lock; this advances the clock past a
    deadline so the test can ask what that transaction believes afterwards.
    """
    with session_scope(settings) as s:
        s.execute(select(func.pg_sleep(seconds)))


def _blocked_backends(settings: Settings) -> int:
    with session_scope(settings) as s:
        return int(
            s.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND state = 'active'"
                )
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# H-8 — a frozen transaction timestamp must not authorize anything
# ---------------------------------------------------------------------------


def test_lock_wait_cannot_authorize_a_step_start_on_an_expired_lease(
    clean_jobs, db_settings
) -> None:
    """The core H-8 reproduction.

    The pre-unit transaction opens while the lease is live, blocks in
    ``_stop_requested``'s row lock, and by the time it acquires the lock the
    lease has expired in real database time. With ``now()`` it saw its own
    frozen start time and authorized; with ``clock_timestamp()`` it must
    stand down having written nothing.
    """
    import continuum_jobs.execution as execution

    job_id, worker_id = _prepare(clean_jobs, _Counter.job_type, lease_seconds=1)
    job = clean_jobs.get(Job, job_id)
    assert job is not None
    plan_units(clean_jobs, job, [UnitSpec("only")])
    clean_jobs.commit()

    blocker_locked = threading.Event()
    release_blocker = threading.Event()
    transaction_started = threading.Event()
    observations: list[tuple[StopReason | None, bool]] = []
    errors: list[BaseException] = []

    def hold_row_lock() -> None:
        with session_scope(db_settings) as blocker:
            blocker.execute(select(Job).where(Job.id == job_id).with_for_update()).scalar_one()
            blocker_locked.set()
            assert release_blocker.wait(60)

    blocker = threading.Thread(target=hold_row_lock, daemon=True)
    blocker.start()
    assert blocker_locked.wait(30), "the blocker never took the row lock"

    def preunit() -> None:
        try:
            with session_scope(db_settings) as session:
                stale = session.get(Job, job_id)
                assert stale is not None
                # Pin transaction_timestamp() while the lease is still live,
                # then block inside the real pre-unit path.
                session.execute(select(func.now())).scalar_one()
                transaction_started.set()
                stop = execution._stop_requested(session, stale, worker_id)
                authorized = False
                if stop is None:
                    authorized = execution._authorize_effect(session, job_id, worker_id, 1)
                    if authorized:
                        step = session.execute(
                            select(JobStep).where(JobStep.job_id == job_id)
                        ).scalar_one()
                        step.status = StepStatus.RUNNING
                        step.started_at = func.clock_timestamp()
                        step.attempt += 1
                session.commit()
                observations.append((stop, authorized))
        # Deliberately BaseException: an escape is itself a finding.
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=preunit, daemon=True)
    worker.start()
    assert transaction_started.wait(30)

    # The pre-unit transaction is now waiting on the blocker's lock. Advance
    # real database time past the one-second lease while it waits.
    _advance_database_clock(db_settings, 1.5)
    release_blocker.set()

    blocker.join(60)
    worker.join(60)
    assert not blocker.is_alive() and not worker.is_alive()
    assert errors == [], f"the pre-unit path raised: {errors}"

    assert observations == [(StopReason.OWNERSHIP_LOST, False)], (
        "H-8: a frozen transaction timestamp authorized a step start on a "
        f"lease that had already expired in real database time: {observations}"
    )

    with session_scope(db_settings) as verify:
        expired = verify.execute(
            select(Job.lease_expires_at < func.clock_timestamp()).where(Job.id == job_id)
        ).scalar_one()
        step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
    assert expired is True, "the lease should be expired by now"
    assert step.status is StepStatus.PENDING, "durable step state was written on a dead lease"
    assert step.attempt == 0
    assert step.started_at is None


def test_lease_liveness_follows_a_clock_that_advances_inside_the_transaction(
    clean_jobs, db_settings
) -> None:
    """The H-8 mechanism in isolation: frozen clock vs advancing clock.

    ``_stop_requested`` acquires the job row lock and only then asks whether
    the lease is alive. Acquiring that lock can block for an unbounded time,
    and ``now()`` does not move while it does. This pins the difference
    directly, with real time passing *inside* one transaction:

    * the frozen ``now()`` still reports the lease as alive;
    * the production check, reading a clock that advanced, reports it dead.

    Against the pre-fix code the second assertion fails, because the check
    used the same frozen clock as the first.

    A note on PostgreSQL semantics learned here: ``clock_timestamp()`` in the
    SET list of an ``UPDATE`` is evaluated *before* that statement waits on a
    row lock, so it does not by itself make a blocked renewal fresh. That is
    harmless in production, because ``_authorize_effect`` renews while this
    transaction already holds the row lock and therefore never waits. It is
    ``_lease_is_alive`` -- which runs after the wait -- that must read an
    advancing clock, and that is what is asserted here.
    """
    import continuum_jobs.execution as execution

    job_id, _worker_id = _prepare(clean_jobs, _Counter.job_type, lease_seconds=1)

    with session_scope(db_settings) as s:
        # Pin transaction_timestamp() while the lease is still live.
        s.execute(select(func.now())).scalar_one()
        # Real database time passes inside this same transaction, exactly as
        # it would while blocking on a row lock.
        s.execute(select(func.pg_sleep(1.5)))

        frozen_says_alive = s.execute(
            select(Job.lease_expires_at > func.now()).where(Job.id == job_id)
        ).scalar_one()
        fresh_says_alive = s.execute(
            select(Job.lease_expires_at > func.clock_timestamp()).where(Job.id == job_id)
        ).scalar_one()

        assert frozen_says_alive is True, (
            "the premise failed: now() should still report the lease as alive"
        )
        assert fresh_says_alive is False, (
            "the premise failed: the lease should be dead by the advancing clock"
        )

        assert execution._lease_is_alive(s, job_id) is False, (
            "H-8: the production liveness check followed the frozen transaction "
            "timestamp and would have authorised a step start on a dead lease"
        )


def test_rightful_owner_is_unaffected_by_the_fresh_clock(clean_jobs, db_settings) -> None:
    """The stricter clock must not cost the ordinary path anything."""
    job_id, worker_id = _prepare(clean_jobs, _Counter.job_type, lease_seconds=30)
    handler = _Counter()

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        reason = execute_job(
            s, job, handler, worker_id=worker_id, settings=db_settings, lease_seconds=30
        )

    assert reason is StopReason.COMPLETED
    assert handler.effects == 1
    with session_scope(db_settings) as verify:
        job = verify.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert job.status is JobStatus.SUCCEEDED
        assert job.units_done == 1
        step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        assert step.status is StepStatus.SUCCEEDED
        assert step.attempt == 1


# ---------------------------------------------------------------------------
# H-9 — the handler must not inherit a pending coordination write
# ---------------------------------------------------------------------------


def test_handler_query_cannot_make_an_expired_job_unreapable(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """The core H-9 reproduction: recovery must stay available.

    A handler performs one harmless query through ``ctx.session`` and then
    blocks. The lease expires. The real reaper must still be able to reclaim
    the job -- the whole promise of the lease model. Before the fix the
    autoflushed ``STEP_STARTED`` insert held a foreign-key lock on the job
    row and ``FOR UPDATE SKIP LOCKED`` skipped it for as long as the handler
    hung.
    """
    import continuum_jobs.execution as execution
    import continuum_jobs.lease as lease

    queried, release = threading.Event(), threading.Event()
    handler = _QueryThenBlock(queried, release)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})
        worker = register_worker(s)
        s.commit()
        claimed = claim_next_job(s, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=1)
        assert claimed is not None
        job_id, worker_id = claimed.id, worker.id

    # The heartbeat has to genuinely stop, or the lease is renewed forever and
    # the question this test asks cannot arise. Making renewal fail is what a
    # stalled or partitioned worker looks like from the database's side: the
    # heartbeat relinquishes ownership after a lease window of failures. Only
    # the heartbeat's binding is patched, so the pre-unit authorisation path
    # still renews normally.
    heartbeat_stopped = threading.Event()
    real_heartbeat = execution.LeaseHeartbeat

    class _ObservedHeartbeat(real_heartbeat):  # type: ignore[valid-type,misc]
        def _run(self) -> None:
            super()._run()
            heartbeat_stopped.set()

    def _unavailable(*_a: Any, **_k: Any) -> bool:
        raise RuntimeError("simulated: the heartbeat cannot reach the database")

    monkeypatch.setattr(execution, "LeaseHeartbeat", _ObservedHeartbeat)
    monkeypatch.setattr(lease, "renew_lease", _unavailable)

    outcomes: list[StopReason] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            with session_scope(db_settings) as s:
                job = s.get(Job, job_id)
                assert job is not None
                outcomes.append(
                    execute_job(
                        s,
                        job,
                        handler,
                        worker_id=worker_id,
                        settings=db_settings,
                        lease_seconds=1,
                        heartbeat_seconds=0.1,
                    )
                )
        # Deliberately BaseException: an escape is itself a finding.
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert queried.wait(30), "the handler never ran its query"
    assert heartbeat_stopped.wait(30), "the heartbeat never relinquished ownership"

    # The step start must already be durable, so the handler holds nothing.
    assert handler.pending_at_effect_start == [False], (
        "H-9: the executor handed the handler a session with unflushed coordination writes"
    )
    with session_scope(db_settings) as verify:
        events = verify.execute(
            select(func.count())
            .select_from(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.event_type == JobEventType.STEP_STARTED)
        ).scalar_one()
    assert events == 1, "STEP_STARTED was not committed with the authorised step start"

    # Let the lease die in real database time while the handler still hangs.
    _advance_database_clock(db_settings, 2.0)

    with session_scope(db_settings) as s:
        recovered = reap_expired_leases(s)
    assert job_id in recovered, (
        "H-9: the reaper could not recover a job whose handler is hung -- "
        "the handler's transaction is holding the job row against "
        "FOR UPDATE SKIP LOCKED"
    )

    with session_scope(db_settings) as verify:
        job = verify.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert job.status is JobStatus.QUEUED
        assert job.lease_owner is None

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST], (
        f"the stale worker did not stand down: {outcomes}"
    )


def test_step_started_commits_with_the_authorized_step_start(clean_jobs, db_settings) -> None:
    """The event and the state it describes land in one transaction.

    Beyond H-9's locking consequence, this is what makes the audit trail
    honest: a STEP_STARTED row that is visible implies the step start it
    describes is visible too.
    """
    queried, release = threading.Event(), threading.Event()
    handler = _QueryThenBlock(queried, release)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})
        worker = register_worker(s)
        s.commit()
        claimed = claim_next_job(s, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30)
        assert claimed is not None
        job_id, worker_id = claimed.id, worker.id

    def run() -> None:
        with session_scope(db_settings) as s:
            job = s.get(Job, job_id)
            assert job is not None
            execute_job(
                s, job, handler, worker_id=worker_id, settings=db_settings, lease_seconds=30
            )

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    assert queried.wait(30)

    # Observed from an entirely separate session: both are committed.
    with session_scope(db_settings) as verify:
        step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        events = verify.execute(
            select(func.count())
            .select_from(JobEvent)
            .where(JobEvent.job_id == job_id, JobEvent.event_type == JobEventType.STEP_STARTED)
        ).scalar_one()
    assert step.status is StepStatus.RUNNING
    assert step.started_at is not None
    assert events == 1

    release.set()
    thread.join(60)
    assert not thread.is_alive()
