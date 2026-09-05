"""Final-audit falsification tests for stale worker ownership.

These tests are audit evidence, not shipped acceptance coverage.  They force
the otherwise narrow boundaries immediately after a handler returns and while
an exception is unwinding.
"""

from __future__ import annotations

import datetime as dt
import threading
import uuid

from continuum_db.enums import JobStatus
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_jobs import (
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec
from sqlalchemy import select, update

pytest_plugins = ["tests.conftest"]


class _SuccessfulHandler:
    job_type = "audit.success"

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, _ctx, _unit):
        return UnitOutcome(result={"landed": True})


class _DelayedFailureHandler:
    job_type = "audit.failure"

    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self.entered = entered
        self.release = release

    def plan(self, _ctx):
        return [UnitSpec("only")]

    def execute_unit(self, _ctx, _unit):
        self.entered.set()
        assert self.release.wait(20)
        raise RuntimeError("deterministic audit failure")


def _prepare(clean_jobs, job_type: str):
    _job, _ = enqueue(clean_jobs, job_type, payload={"audit": str(uuid.uuid4())})
    worker_a = register_worker(clean_jobs)
    worker_b = register_worker(clean_jobs)
    clean_jobs.commit()
    claimed = claim_next_job(
        clean_jobs, worker_id=worker_a.id, resource_classes=["cpu"], lease_seconds=30
    )
    clean_jobs.commit()
    assert claimed is not None
    return claimed.id, worker_a.id, worker_b.id


def _steal(settings, job_id: uuid.UUID, worker_b: uuid.UUID) -> None:
    with session_scope(settings) as session:
        session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(lease_expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1))
        )
    with session_scope(settings) as session:
        assert job_id in reap_expired_leases(session)
    with session_scope(settings) as session:
        claimed = claim_next_job(
            session, worker_id=worker_b, resource_classes=["cpu"], lease_seconds=300
        )
        assert claimed is not None and claimed.id == job_id


def _observe(settings, job_id: uuid.UUID) -> tuple[JobStatus, uuid.UUID | None]:
    with session_scope(settings) as session:
        row = session.execute(select(Job).where(Job.id == job_id)).scalar_one()
        return row.status, row.lease_owner


def test_stale_worker_cannot_finalize_after_post_handler_reclaim(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """H-1: reclaim in the gap after the heartbeat context has exited."""
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs, _SuccessfulHandler.job_type)
    reached_post_unit_renew = threading.Event()
    release_worker_a = threading.Event()
    real_renew = execution.renew_lease

    def paused_renew(session, target_job_id, lease_seconds, *, worker_id=None):
        # execute_job's between-unit call omits worker_id.  LeaseHeartbeat uses
        # the function in continuum_jobs.lease and is unaffected by this hook.
        if target_job_id == job_id and worker_id is None:
            reached_post_unit_renew.set()
            assert release_worker_a.wait(20)
        return real_renew(session, target_job_id, lease_seconds, worker_id=worker_id)

    monkeypatch.setattr(execution, "renew_lease", paused_renew)
    outcomes: list[StopReason] = []

    def run_a() -> None:
        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            outcomes.append(
                execute_job(
                    session,
                    job,
                    _SuccessfulHandler(),
                    worker_id=worker_a,
                    settings=db_settings,
                    lease_seconds=30,
                    heartbeat_seconds=0.1,
                )
            )

    thread = threading.Thread(target=run_a, daemon=True)
    thread.start()
    assert reached_post_unit_renew.wait(20)
    _steal(db_settings, job_id, worker_b)
    assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)
    release_worker_a.set()
    thread.join(20)
    assert not thread.is_alive()

    # A no longer owns the job and must stand down without changing B's row.
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)


def test_handler_exception_after_ownership_loss_cannot_fail_new_owner_job(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """H-2: ownership loss must dominate an exception from stale worker A."""
    import continuum_jobs.lease as lease

    job_id, worker_a, worker_b = _prepare(clean_jobs, _DelayedFailureHandler.job_type)
    entered = threading.Event()
    release = threading.Event()
    heartbeat_observed_loss = threading.Event()
    outcomes: list[StopReason] = []
    real_renew = lease.renew_lease

    def observed_renew(session, target_job_id, lease_seconds, *, worker_id=None):
        renewed = real_renew(session, target_job_id, lease_seconds, worker_id=worker_id)
        if target_job_id == job_id and worker_id == worker_a and not renewed:
            heartbeat_observed_loss.set()
        return renewed

    monkeypatch.setattr(lease, "renew_lease", observed_renew)

    def run_a() -> None:
        with session_scope(db_settings) as session:
            job = session.get(Job, job_id)
            assert job is not None
            outcomes.append(
                execute_job(
                    session,
                    job,
                    _DelayedFailureHandler(entered, release),
                    worker_id=worker_a,
                    settings=db_settings,
                    lease_seconds=3,
                    heartbeat_seconds=0.1,
                )
            )

    thread = threading.Thread(target=run_a, daemon=True)
    thread.start()
    assert entered.wait(20)
    _steal(db_settings, job_id, worker_b)
    assert heartbeat_observed_loss.wait(20)
    release.set()
    thread.join(20)
    assert not thread.is_alive()

    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)


def test_transition_rejects_a_stale_unlocked_orm_snapshot(clean_jobs, db_settings) -> None:
    """H-3: transition validation must be atomic with the status write."""
    from continuum_jobs import transition

    job_id, worker_a, worker_b = _prepare(clean_jobs, "audit.transition")
    with session_scope(db_settings) as stale_session:
        stale = stale_session.get(Job, job_id)
        assert stale is not None and stale.lease_owner == worker_a
        _steal(db_settings, job_id, worker_b)
        transition(stale_session, stale, JobStatus.SUCCEEDED, worker_id=worker_a)

    assert _observe(db_settings, job_id) == (JobStatus.RUNNING, worker_b)
