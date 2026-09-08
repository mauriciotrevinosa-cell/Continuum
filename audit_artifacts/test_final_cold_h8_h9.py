"""Final cold-audit PostgreSQL falsification tests for H-8 and H-9."""

from __future__ import annotations

import threading
import uuid

import pytest
from continuum_db.enums import JobStatus, StepStatus
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
from sqlalchemy import func, select

pytest_plugins = ["tests.conftest"]
pytestmark = pytest.mark.requires_db


class _EffectCounter:
    job_type = "audit.final-cold"

    def __init__(self) -> None:
        self.effects = 0

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, _ctx, _unit):
        self.effects += 1
        return UnitOutcome()


class _QueryThenBlock:
    job_type = "audit.final-cold-query"

    def __init__(self, queried: threading.Event, release: threading.Event) -> None:
        self.queried = queried
        self.release = release

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, ctx, _unit):
        # This harmless query triggers SQLAlchemy autoflush of STEP_STARTED.
        ctx.session.execute(select(func.count()).select_from(JobStep)).scalar_one()
        self.queried.set()
        assert self.release.wait(30)
        return UnitOutcome()


def _prepare(session, job_type: str, *, lease_seconds: int = 1):
    _job, _ = enqueue(session, job_type, payload={"audit": str(uuid.uuid4())})
    worker = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=lease_seconds
    )
    session.commit()
    assert claimed is not None
    return claimed.id, worker.id


def _run(settings, job_id, worker_id, handler, *, lease_seconds=1):
    outcomes: list[StopReason] = []
    errors: list[BaseException] = []

    def target() -> None:
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
                        lease_seconds=lease_seconds,
                        heartbeat_seconds=0.1,
                    )
                )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    return thread, outcomes, errors


def test_h8_lock_wait_cannot_authorize_expired_step_start(clean_jobs, db_settings) -> None:
    """A stale transaction timestamp must not authorize durable step mutation."""
    import continuum_jobs.execution as execution

    job_id, worker_id = _prepare(clean_jobs, _EffectCounter.job_type)
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
            assert release_blocker.wait(30)

    blocker = threading.Thread(target=hold_row_lock, daemon=True)
    blocker.start()
    assert blocker_locked.wait(30)

    def preunit_transaction() -> None:
        try:
            with session_scope(db_settings) as session:
                stale = session.get(Job, job_id)
                assert stale is not None
                # Establish transaction_timestamp() while the lease is live,
                # then block in the real _stop_requested row lock.
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
                    step.attempt += 1
                session.commit()
                observations.append((stop, authorized))
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=preunit_transaction, daemon=True)
    worker.start()
    assert transaction_started.wait(30)

    # clock_timestamp() advances during the lock wait; now() does not.
    with session_scope(db_settings) as observer:
        observer.execute(select(func.pg_sleep(1.5))).scalar_one_or_none()
    release_blocker.set()
    blocker.join(30)
    worker.join(30)
    assert not blocker.is_alive() and not worker.is_alive()
    assert errors == []
    assert observations == [(StopReason.OWNERSHIP_LOST, False)]

    # The separate fresh probe still prevents the subsequent effect, but it
    # occurs only after the stale transaction has committed the step mutation.
    assert execution._owns_live_lease(db_settings, job_id, worker_id) is False

    with session_scope(db_settings) as verify:
        step = verify.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        expired = verify.execute(
            select(Job.lease_expires_at < func.clock_timestamp()).where(Job.id == job_id)
        ).scalar_one()
    assert expired is True
    assert step.status is StepStatus.PENDING
    assert step.attempt == 0


def test_h9_handler_query_cannot_make_expired_job_unreapable(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """A handler read must not flush an FK lock that defeats SKIP LOCKED recovery."""
    import continuum_jobs.execution as execution
    import continuum_jobs.lease as lease

    job_id, worker_id = _prepare(clean_jobs, _QueryThenBlock.job_type)
    queried = threading.Event()
    release = threading.Event()
    heartbeat_stopped = threading.Event()
    real_heartbeat = execution.LeaseHeartbeat

    class ObservedHeartbeat(real_heartbeat):
        def _run(self):
            super()._run()
            heartbeat_stopped.set()

    def unrecoverable_renew(*_args, **_kwargs):
        raise RuntimeError("audit: heartbeat database unavailable")

    monkeypatch.setattr(execution, "LeaseHeartbeat", ObservedHeartbeat)
    monkeypatch.setattr(lease, "renew_lease", unrecoverable_renew)
    worker, outcomes, errors = _run(
        db_settings, job_id, worker_id, _QueryThenBlock(queried, release)
    )
    assert queried.wait(30)
    assert heartbeat_stopped.wait(30)

    with session_scope(db_settings) as observer:
        observer.execute(select(func.pg_sleep(1.2))).scalar_one_or_none()
        assert observer.execute(
            select(Job.lease_expires_at < func.clock_timestamp()).where(Job.id == job_id)
        ).scalar_one()
        # Confirm the pending event really autoflushed in the still-open
        # handler transaction; it is invisible here but its backend is active.
        assert (
            observer.execute(
                select(func.count()).select_from(JobEvent).where(JobEvent.job_id == job_id)
            ).scalar_one()
            >= 2
        )

    with session_scope(db_settings) as reaper:
        recovered = reap_expired_leases(reaper)

    release.set()
    worker.join(30)
    assert not worker.is_alive()
    assert errors == []
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert job_id in recovered
    with session_scope(db_settings) as verify:
        job = verify.get(Job, job_id)
        assert job is not None
        assert job.status is JobStatus.QUEUED
