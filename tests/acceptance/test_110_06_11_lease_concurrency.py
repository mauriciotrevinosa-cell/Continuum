"""Lease concurrency regression suite — second audit finding C-1.

**The defect.** ``reap_expired_leases()`` read stale jobs without a lock,
decided from that snapshot, and wrote ``QUEUED`` later. A live worker could
commit a fresh heartbeat in the gap, and the reaper would then overwrite it,
moving genuinely ``RUNNING`` work back to ``QUEUED`` so a second worker could
claim it. ``renew_lease()`` matched on job id alone, so a worker that had
already lost the job could push its lease forward anyway.

Content addressing keeps the stored artifact correct under duplicate
execution, but it does nothing about duplicate compute and nothing at all
about an effect that is not content-addressed. This violates F-27 and
ADR-0002 §5.

**Why these tests are shaped this way.** The race is made deterministic with
a real row lock and a barrier, not with sleeps. A test that merely made the
window narrow would pass on a fast machine and hide the defect again. Every
test here uses real PostgreSQL, because the invariant *is* a PostgreSQL
concurrency guarantee — a mocked session cannot express it.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from continuum_config import Settings
from continuum_core import JobStatus
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_jobs import (
    LeaseHeartbeat,
    claim_next_job,
    enqueue,
    reap_expired_leases,
    register_worker,
    renew_lease,
)
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.requires_db


def _db_now(session: Session):
    return session.execute(select(func.now())).scalar_one()


def _await_reaper_settled(
    session: Session, done: threading.Event, *, timeout: float = 20.0
) -> None:
    """Wait until the reaper has either blocked on the locked row or finished.

    Synchronising on observable database state rather than sleeping a guessed
    interval. Both outcomes are legitimate and the distinction is exactly the
    fix:

    * **broken** — the unlocked SELECT returns the stale row, so the reaper
      proceeds and its UPDATE blocks on the row this test holds;
    * **fixed** — ``FOR UPDATE SKIP LOCKED`` skips the contended row, so the
      reaper finishes immediately without touching it.

    Waiting for *either* keeps the interleaving deterministic in both cases,
    so the test reproduces the defect against the old code and passes against
    the new one for the right reason.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if done.is_set():
            return
        waiting = session.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
            )
        ).scalar_one()
        if waiting:
            return
        time.sleep(0.02)
    raise AssertionError("the reaper neither blocked nor finished; the race never happened")


def _expire_lease(session: Session, job: Job, seconds_ago: int = 30) -> None:
    """Push a lease into the past using the DATABASE clock (D-09)."""
    job.lease_expires_at = session.execute(
        select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, seconds_ago))
    ).scalar_one()
    session.commit()


def _running_job(session: Session, *, lease_seconds: int = 30) -> tuple[Job, uuid.UUID]:
    _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1})
    worker = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=lease_seconds
    )
    session.commit()
    assert claimed is not None
    return claimed, worker.id


class TestReaperStillWorks:
    """Guard the guard: the fix must not simply stop the reaper working."""

    def test_genuinely_abandoned_lease_is_still_reaped(self, clean_jobs) -> None:
        session = clean_jobs
        job, _worker_id = _running_job(session)
        _expire_lease(session, job)

        recovered = reap_expired_leases(session)
        session.commit()
        session.refresh(job)

        assert job.id in recovered
        assert job.status is JobStatus.QUEUED
        assert job.lease_owner is None
        assert job.attempt == 1

    def test_a_live_lease_is_never_reaped(self, clean_jobs) -> None:
        session = clean_jobs
        job, worker_id = _running_job(session, lease_seconds=300)

        recovered = reap_expired_leases(session)
        session.commit()
        session.refresh(job)

        assert job.id not in recovered
        assert job.status is JobStatus.RUNNING
        assert job.lease_owner == worker_id


class TestOrdinaryRenewal:
    def test_heartbeat_renews_a_live_lease(self, clean_jobs) -> None:
        session = clean_jobs
        job, worker_id = _running_job(session, lease_seconds=30)
        before = job.lease_expires_at

        assert renew_lease(session, job.id, 300, worker_id=worker_id) is True
        session.commit()
        session.refresh(job)

        assert job.lease_expires_at > before

    def test_renewal_rescues_a_job_from_the_reaper(self, clean_jobs) -> None:
        """Renewal is only meaningful if it actually prevents reaping."""
        session = clean_jobs
        job, worker_id = _running_job(session)
        _expire_lease(session, job)

        assert renew_lease(session, job.id, 300, worker_id=worker_id) is True
        session.commit()

        recovered = reap_expired_leases(session)
        session.commit()
        session.refresh(job)

        assert job.id not in recovered
        assert job.status is JobStatus.RUNNING


class TestRenewalValidatesOwnership:
    """``renew_lease`` must not blindly renew by job id."""

    def test_a_different_worker_cannot_renew(self, clean_jobs) -> None:
        session = clean_jobs
        job, owner_id = _running_job(session)
        interloper = register_worker(session)
        session.commit()

        assert renew_lease(session, job.id, 300, worker_id=interloper.id) is False
        session.commit()
        session.refresh(job)
        assert job.lease_owner == owner_id

    def test_a_job_no_longer_running_cannot_be_renewed(self, clean_jobs) -> None:
        """The lease exists to describe RUNNING work. Renewing a job that has
        finished, been cancelled or been requeued papers over exactly the
        condition the lease is meant to expose."""
        session = clean_jobs
        job, worker_id = _running_job(session)
        _expire_lease(session, job)
        reap_expired_leases(session)
        session.commit()
        session.refresh(job)
        assert job.status is JobStatus.QUEUED

        assert renew_lease(session, job.id, 300, worker_id=worker_id) is False
        session.commit()

    def test_an_unknown_job_cannot_be_renewed(self, clean_jobs) -> None:
        session = clean_jobs
        assert renew_lease(session, uuid.uuid4(), 300, worker_id=uuid.uuid4()) is False


class TestStaleReaperSnapshot:
    """C-1 proper: the reaper must not act on an observation the database has
    already superseded."""

    def test_fresh_heartbeat_cannot_be_overwritten_by_a_stale_snapshot(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """The auditor's reproduction, promoted to permanent coverage.

        A holder locks the row and writes a future lease *without committing*.
        The reaper runs concurrently: with the fix it blocks on the lock
        rather than deciding from the pre-heartbeat snapshot, and once the
        holder commits, PostgreSQL re-evaluates the predicate against the new
        row version — so the row is no longer stale and is not reaped.

        Deterministic by construction: the ordering is enforced by a real row
        lock and a barrier, never by sleeping.
        """
        session = clean_jobs
        job, worker_id = _running_job(session)
        job_id = job.id
        _expire_lease(session, job)

        reaper_started = threading.Barrier(2, timeout=30)
        reaper_done = threading.Event()
        reaped: list[uuid.UUID] = []

        def reap() -> None:
            try:
                with session_scope(db_settings) as reaper_session:
                    reaper_started.wait()
                    reaped.extend(reap_expired_leases(reaper_session))
            finally:
                reaper_done.set()

        holder = Session(bind=session.get_bind(), expire_on_commit=False)
        try:
            live = holder.execute(
                select(Job).where(Job.id == job_id).with_for_update()
            ).scalar_one()
            live.lease_expires_at = holder.execute(
                select(func.now() + func.make_interval(0, 0, 0, 0, 0, 0, 300))
            ).scalar_one()
            holder.flush()  # holds the row lock; not yet committed

            thread = threading.Thread(target=reap, daemon=True)
            thread.start()
            reaper_started.wait(timeout=30)

            # Proceed only once the reaper is provably blocked on the row this
            # test holds. Without this the reaper might run entirely after the
            # commit, and the test would pass even against the defect.
            _await_reaper_settled(session, reaper_done)

            # Release the fresh lease. It must remain visible, not overwritten
            # by the reaper's earlier observation.
            holder.commit()
            thread.join(timeout=30)
            assert reaper_done.is_set(), "the reaper never finished"
        finally:
            holder.close()

        session.expire_all()
        observed = session.get(Job, job_id)
        assert observed is not None
        assert observed.status is JobStatus.RUNNING, (
            "the reaper overwrote a fresh heartbeat using a stale pre-heartbeat snapshot"
        )
        assert observed.lease_owner == worker_id
        assert job_id not in reaped
        assert observed.lease_expires_at > _db_now(session)

    def test_two_workers_cannot_own_the_same_live_job_through_this_race(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """The consequence that makes C-1 critical.

        If the stale reaper wins, the job returns to QUEUED and a second
        worker claims work the first is still executing.
        """
        session = clean_jobs
        job, worker_a = _running_job(session)
        job_id = job.id
        worker_b = register_worker(session)
        session.commit()
        worker_b_id = worker_b.id
        _expire_lease(session, job)

        started = threading.Barrier(2, timeout=30)
        claimer_done = threading.Event()
        stolen: list[uuid.UUID] = []

        def reap_then_claim() -> None:
            try:
                with session_scope(db_settings) as other:
                    started.wait()
                    reap_expired_leases(other)
                    got = claim_next_job(
                        other, worker_id=worker_b_id, resource_classes=["cpu"], lease_seconds=30
                    )
                    if got is not None:
                        stolen.append(got.id)
            finally:
                claimer_done.set()

        holder = Session(bind=session.get_bind(), expire_on_commit=False)
        try:
            live = holder.execute(
                select(Job).where(Job.id == job_id).with_for_update()
            ).scalar_one()
            live.lease_expires_at = holder.execute(
                select(func.now() + func.make_interval(0, 0, 0, 0, 0, 0, 300))
            ).scalar_one()
            holder.flush()

            thread = threading.Thread(target=reap_then_claim, daemon=True)
            thread.start()
            started.wait(timeout=30)
            _await_reaper_settled(session, claimer_done)
            holder.commit()
            thread.join(timeout=30)
        finally:
            holder.close()

        session.expire_all()
        observed = session.get(Job, job_id)
        assert observed is not None
        assert stolen == [], "a second worker claimed a job that was still running"
        assert observed.lease_owner == worker_a
        assert observed.status is JobStatus.RUNNING

    def test_concurrent_reapers_do_not_double_reap(self, clean_jobs, db_settings: Settings) -> None:
        """Two reapers racing on a genuinely expired job must recover it once,
        not increment the attempt counter twice."""
        session = clean_jobs
        job, _worker_id = _running_job(session)
        job_id = job.id
        _expire_lease(session, job)

        ready = threading.Barrier(2, timeout=30)
        results: list[list[uuid.UUID]] = []
        lock = threading.Lock()

        def reap() -> None:
            with session_scope(db_settings) as s:
                ready.wait()
                got = reap_expired_leases(s)
            with lock:
                results.append(got)

        threads = [threading.Thread(target=reap, daemon=True) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive()

        session.expire_all()
        observed = session.get(Job, job_id)
        assert observed is not None
        assert observed.attempt == 1, f"job was reaped more than once: attempt={observed.attempt}"
        assert sum(job_id in r for r in results) == 1


class TestHeartbeatDoesNotFakeOwnership:
    """A worker that has genuinely lost the job must not carry on as owner."""

    def test_heartbeat_stops_and_reports_when_ownership_is_lost(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        session = clean_jobs
        job, worker_id = _running_job(session, lease_seconds=3)
        job_id = job.id

        with LeaseHeartbeat(
            db_settings,
            job_id=job_id,
            worker_id=worker_id,
            lease_seconds=3,
            interval_seconds=0.2,
        ) as beat:
            # Take the job away, exactly as the reaper would after a genuine
            # crash, then let the heartbeat discover it.
            with session_scope(db_settings) as thief:
                stolen = thief.get(Job, job_id)
                assert stolen is not None
                _expire_lease(thief, stolen)
                reap_expired_leases(thief)

            deadline = threading.Event()
            for _ in range(60):
                if beat.ownership_lost:
                    break
                deadline.wait(0.1)

        assert beat.ownership_lost, (
            "the heartbeat kept renewing after the job was taken away; a worker "
            "that has lost ownership must not continue as if it were still valid"
        )

    def test_heartbeat_does_not_resurrect_a_reaped_job(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """The renewal guard's real purpose: a losing worker must not be able
        to drag a requeued job back into a live-lease state."""
        session = clean_jobs
        job, worker_id = _running_job(session)
        job_id = job.id
        _expire_lease(session, job)
        reap_expired_leases(session)
        session.commit()
        session.refresh(job)
        assert job.status is JobStatus.QUEUED
        assert job.lease_owner is None

        assert renew_lease(session, job_id, 300, worker_id=worker_id) is False
        session.commit()
        session.refresh(job)

        assert job.status is JobStatus.QUEUED
        assert job.lease_owner is None
        assert job.lease_expires_at is None

    def test_persistent_heartbeat_failure_relinquishes_ownership(
        self, clean_jobs, db_settings: Settings
    ) -> None:
        """If renewal keeps failing for longer than the lease, the lease has
        expired as far as every other worker is concerned. Continuing to
        behave as the owner is the fiction this must not allow."""
        session = clean_jobs
        job, worker_id = _running_job(session, lease_seconds=2)

        broken = Settings(
            _env_file=None,
            data_home=str(db_settings.data_home),
            source_vault_root=str(db_settings.source_vault_root),
            database_url="postgresql+psycopg://continuum:wrong@127.0.0.1:5433/continuum_missing",
        )

        with LeaseHeartbeat(
            broken,
            job_id=job.id,
            worker_id=worker_id,
            lease_seconds=2,
            interval_seconds=0.2,
        ) as beat:
            waiter = threading.Event()
            for _ in range(120):
                if beat.ownership_lost:
                    break
                waiter.wait(0.1)

        assert beat.errors > 0, "the failure path never ran"
        assert beat.ownership_lost, (
            "the heartbeat swallowed failures indefinitely; after a full lease "
            "window of failed renewals it must stop claiming ownership"
        )

        from continuum_db.session import dispose_engine

        dispose_engine(broken)
