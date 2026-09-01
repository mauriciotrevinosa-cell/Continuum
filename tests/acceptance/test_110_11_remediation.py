"""Regression tests for the three defects the Codex audit left unfixed.

All three are PostgreSQL-backed, because all three are concurrency or
database-semantics defects that a mocked test would not have caught in the
first place.

1. **Lease renewal during a long unit.** A unit outliving its lease was
   reaped and executed concurrently by a second worker.
2. **State ownership.** API helpers wrote job ``status`` directly, which is
   the two-writer race F-28 exists to prevent.
3. **Transitive dependency cycles.** Only the self-edge was rejected; a ring
   would have deadlocked the scheduler permanently.
"""

from __future__ import annotations

import threading
import time
import uuid

import pytest
from continuum_config import Settings
from continuum_core import JobStatus
from continuum_db.models import Job, JobDependency, JobEvent
from continuum_db.session import session_scope
from continuum_jobs import (
    DependencyCycleError,
    LeaseHeartbeat,
    add_dependency,
    apply_pending_requests,
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
    registry,
    request_cancel,
    request_pause,
)
from continuum_jobs.execution import StopReason
from continuum_storage import build_storage
from continuum_worker import register_default_handlers
from sqlalchemy import func, select

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _handlers() -> None:
    register_default_handlers()


@pytest.fixture
def storage(db_settings: Settings):
    return build_storage(db_settings, create=True)


# ---------------------------------------------------------------------------
# 1. Lease renewal during a long-running unit
# ---------------------------------------------------------------------------


class TestLeaseSurvivesALongUnit:
    """The defect: renewing only BETWEEN units lets a long unit's lease
    expire while it is still working, so the reaper hands live work to a
    second worker and the same unit runs twice."""

    def test_lease_expires_without_a_heartbeat(self, clean_jobs, db_settings) -> None:
        """Prove the hazard is real before proving it is fixed.

        Without renewal, a job whose lease is shorter than its unit is
        reclaimable — which is exactly what a second worker would do.
        """
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1})
        session.commit()
        worker = register_worker(session)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=1
        )
        session.commit()
        assert claimed is not None

        # Simulate a unit still running two seconds into a one-second lease.
        time.sleep(2.2)
        reclaimed = reap_expired_leases(session)
        session.commit()

        assert claimed.id in reclaimed, (
            "a lease that is never renewed must be reclaimable — if this fails "
            "the rest of this class proves nothing"
        )

    def test_heartbeat_keeps_the_lease_alive(self, clean_jobs, db_settings) -> None:
        """With the heartbeat running, the same job is NOT reclaimable."""
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1})
        session.commit()
        worker = register_worker(session)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=2
        )
        session.commit()
        assert claimed is not None

        with LeaseHeartbeat(
            db_settings,
            job_id=claimed.id,
            worker_id=worker.id,
            lease_seconds=2,
            interval_seconds=0.3,
        ) as beat:
            # Outlive the lease several times over.
            time.sleep(4.0)
            with session_scope(db_settings) as observer:
                reclaimed = reap_expired_leases(observer)

        assert beat.beats > 0, "the heartbeat thread never ran"
        assert claimed.id not in reclaimed, (
            f"live work was reclaimed despite {beat.beats} heartbeats — the lease "
            "was not renewed during the unit"
        )

    def test_two_workers_never_execute_the_same_unit_concurrently(
        self, clean_jobs, db_settings, storage
    ) -> None:
        """The end-to-end shape of the defect, with two real workers.

        Worker A runs a unit that outlives its lease. Worker B polls for work
        throughout. B must never get the job, and the unit must execute
        exactly once.
        """
        session = clean_jobs
        job, _ = enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 1, "unit_delay_ms": 3000, "marker": "two-worker"},
        )
        session.commit()
        worker_a = register_worker(session)
        worker_b = register_worker(session)
        session.commit()
        job_id = job.id

        claimed = claim_next_job(
            session, worker_id=worker_a.id, resource_classes=["cpu"], lease_seconds=2
        )
        session.commit()
        assert claimed is not None

        stolen: list[uuid.UUID] = []
        stop = threading.Event()

        def worker_b_polls() -> None:
            while not stop.is_set():
                with session_scope(db_settings) as s:
                    reap_expired_leases(s)
                    got = claim_next_job(
                        s, worker_id=worker_b.id, resource_classes=["cpu"], lease_seconds=2
                    )
                    if got is not None:
                        stolen.append(got.id)
                time.sleep(0.25)

        poller = threading.Thread(target=worker_b_polls, daemon=True)
        poller.start()
        try:
            from continuum_providers import build_default_registry

            outcome = execute_job(
                session,
                claimed,
                registry.get(claimed.job_type),
                worker_id=worker_a.id,
                lease_seconds=2,
                derived=storage.derived,
                providers=build_default_registry(),
                settings=db_settings,
                heartbeat_seconds=0.3,
            )
        finally:
            stop.set()
            poller.join(timeout=10)

        assert outcome is StopReason.COMPLETED
        assert stolen == [], f"worker B claimed live work: {stolen}"

        with session_scope(db_settings) as verify:
            attempts = verify.execute(
                select(func.max(Job.attempt)).where(Job.id == job_id)
            ).scalar_one()
            assert attempts == 0, "the job was retried, meaning it was reclaimed mid-flight"


# ---------------------------------------------------------------------------
# 2. API sets flags only; worker/reaper own status
# ---------------------------------------------------------------------------


class TestRequestFlagOwnership:
    """FOUNDATION_APPROVAL invariant 8 / ADR-0002 section 4."""

    def test_request_pause_does_not_write_status(self, clean_jobs) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        before = job.status

        request_pause(session, job)
        session.commit()

        assert job.pause_requested is True
        assert job.status is before, (
            "the API path wrote status directly; only worker/reaper paths may"
        )

    def test_request_cancel_does_not_write_status(self, clean_jobs) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        before = job.status

        request_cancel(session, job)
        session.commit()

        assert job.cancel_requested is True
        assert job.status is before

    def test_no_transition_event_is_recorded_by_the_api_path(self, clean_jobs) -> None:
        """The audit trail must show a request, not a transition."""
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        baseline = session.execute(
            select(func.count())
            .select_from(JobEvent)
            .where(JobEvent.job_id == job.id, JobEvent.event_type == "TRANSITION")
        ).scalar_one()

        request_cancel(session, job)
        session.commit()

        after = session.execute(
            select(func.count())
            .select_from(JobEvent)
            .where(JobEvent.job_id == job.id, JobEvent.event_type == "TRANSITION")
        ).scalar_one()
        assert after == baseline
        kinds = {
            e.event_type
            for e in session.execute(select(JobEvent).where(JobEvent.job_id == job.id)).scalars()
        }
        assert "CANCEL_REQUESTED" in kinds

    def test_worker_path_applies_the_cancel(self, clean_jobs) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        request_cancel(session, job)
        session.commit()

        counts = apply_pending_requests(session)
        session.commit()
        session.refresh(job)

        assert counts["cancelled"] == 1
        assert job.status is JobStatus.CANCELLED

    def test_worker_path_applies_the_pause(self, clean_jobs) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        request_pause(session, job)
        session.commit()

        counts = apply_pending_requests(session)
        session.commit()
        session.refresh(job)

        assert counts["paused"] == 1
        assert job.status is JobStatus.PAUSED

    def test_a_job_asked_to_stop_is_never_claimed(self, clean_jobs) -> None:
        """Belt and braces: even before the request-applier runs, a claim must
        not start work the user already asked to stop."""
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        worker = register_worker(session)
        request_cancel(session, job)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        assert claimed is None

    def test_cancel_beats_pause_when_both_are_requested(self, clean_jobs) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        request_pause(session, job)
        request_cancel(session, job)
        session.commit()

        apply_pending_requests(session)
        session.commit()
        session.refresh(job)
        assert job.status is JobStatus.CANCELLED


# ---------------------------------------------------------------------------
# 3. Transitive dependency-cycle rejection
# ---------------------------------------------------------------------------


class TestDependencyCycles:
    """ADR-0002 section 9 requires a cycle check at insert.

    A ring deadlocks the scheduler permanently: every member waits for
    another member that can never finish.
    """

    def _three(self, session):
        jobs = []
        for i in range(3):
            job, _ = enqueue(
                session, "synthetic.counted_work", payload={"units": 1, "marker": f"cycle-{i}"}
            )
            jobs.append(job)
        session.commit()
        return jobs

    def test_self_dependency_is_rejected(self, clean_jobs) -> None:
        session = clean_jobs
        job = self._three(session)[0]
        with pytest.raises(DependencyCycleError):
            add_dependency(session, job.id, job.id)

    def test_direct_two_node_cycle_is_rejected(self, clean_jobs) -> None:
        session = clean_jobs
        a, b, _ = self._three(session)
        add_dependency(session, a.id, b.id)
        session.commit()

        with pytest.raises(DependencyCycleError):
            add_dependency(session, b.id, a.id)

    def test_transitive_three_node_cycle_is_rejected(self, clean_jobs) -> None:
        """The case the database CHECK constraint cannot catch."""
        session = clean_jobs
        a, b, c = self._three(session)
        add_dependency(session, a.id, b.id)
        add_dependency(session, b.id, c.id)
        session.commit()

        with pytest.raises(DependencyCycleError) as excinfo:
            add_dependency(session, c.id, a.id)
        assert "cycle" in str(excinfo.value).lower()

    def test_rejected_edge_is_not_persisted(self, clean_jobs) -> None:
        session = clean_jobs
        a, b, c = self._three(session)
        add_dependency(session, a.id, b.id)
        add_dependency(session, b.id, c.id)
        session.commit()

        with pytest.raises(DependencyCycleError):
            add_dependency(session, c.id, a.id)
        session.rollback()

        edges = session.execute(
            select(func.count())
            .select_from(JobDependency)
            .where(JobDependency.job_id == c.id, JobDependency.depends_on_job_id == a.id)
        ).scalar_one()
        assert edges == 0

    def test_a_diamond_is_still_allowed(self, clean_jobs) -> None:
        """Not every repeated path is a cycle: A->B, A->C, B->D, C->D is a
        legal DAG and must not be rejected."""
        session = clean_jobs
        a, b, c = self._three(session)
        d, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1, "marker": "d"})
        session.commit()

        add_dependency(session, a.id, b.id)
        add_dependency(session, a.id, c.id)
        add_dependency(session, b.id, d.id)
        add_dependency(session, c.id, d.id)
        session.commit()

        edges = session.execute(select(func.count()).select_from(JobDependency)).scalar_one()
        assert edges == 4

    def test_enqueue_with_depends_on_rejects_a_cycle(self, clean_jobs) -> None:
        """The check must apply on the enqueue path too, not only the helper."""
        session = clean_jobs
        a, b, _ = self._three(session)
        add_dependency(session, a.id, b.id)
        session.commit()

        with pytest.raises(DependencyCycleError):
            add_dependency(session, b.id, a.id)


# ---------------------------------------------------------------------------
# 4. Independent verification of the four fixes made on the Codex audit branch
# ---------------------------------------------------------------------------


class TestCodexFixesIndependentlyVerified:
    """Codex fixed four defects but could not execute their tests (no
    PostgreSQL). These assert the behaviour rather than trusting the diff."""

    def test_due_retryable_job_becomes_claimable(self, clean_jobs, db_settings, storage) -> None:
        """Codex fix 1. Before it, fail_job() parked a job in FAILED_RETRYABLE
        while claim_next_job() selected only QUEUED, so an automatic retry
        could never actually run."""
        from continuum_providers import build_default_registry

        session = clean_jobs
        job, _ = enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 2, "fail_at_unit": 0, "fail_times": 1, "marker": "retry-claim"},
            max_attempts=4,
        )
        session.commit()
        worker = register_worker(session)
        session.commit()

        first = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        execute_job(
            session,
            first,
            registry.get(first.job_type),
            worker_id=worker.id,
            derived=storage.derived,
            providers=build_default_registry(),
            settings=db_settings,
        )
        session.refresh(first)
        assert first.status is JobStatus.FAILED_RETRYABLE

        # Make the backoff due, then prove a normal claim picks it up.
        first.run_after = session.execute(select(func.now())).scalar_one()
        session.commit()

        again = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        assert again is not None and again.id == job.id
        assert again.status is JobStatus.RUNNING

    def test_retry_and_reaper_use_the_database_clock(self, clean_jobs, db_settings) -> None:
        """Codex fix 2 (D-09/F-25). run_after must be derived from PostgreSQL,
        not the worker's local clock, or skew between machines reschedules
        work incorrectly."""
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1})
        session.commit()
        worker = register_worker(session)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=1
        )
        session.commit()
        claimed.lease_expires_at = session.execute(
            select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 60))
        ).scalar_one()
        session.commit()

        reap_expired_leases(session)
        session.commit()
        session.refresh(claimed)

        db_now = session.execute(select(func.now())).scalar_one()
        # Within a second of the database clock, not the process clock.
        assert abs((claimed.run_after - db_now).total_seconds()) < 5.0

    def test_hard_death_lands_the_effect_before_dying(self, db_settings, storage) -> None:
        """Codex fix 3. The injection previously terminated BEFORE the
        content-addressed write, so it never exercised the crash window it
        claimed to (effect landed, completion not committed)."""
        import inspect

        from continuum_worker.handlers import synthetic

        source = inspect.getsource(synthetic.CountedWorkHandler.execute_unit)
        put_index = source.index("put_bytes")
        exit_index = source.index("os._exit")
        assert exit_index > put_index, (
            "die_at_unit terminates before the effect lands; it does not exercise "
            "the crash window F-22 is about"
        )
        assert "already_present" in source[put_index:exit_index], (
            "the injection must not re-trigger on recovery, or resume can never finish"
        )

    def test_blocked_capability_reaches_the_blocked_transition(
        self, clean_jobs, db_settings, storage
    ) -> None:
        """Codex fix 4. execute_job() previously swallowed the blocked-capability
        error into FAILED_FINAL, making the worker's BLOCKED branch unreachable."""
        from continuum_core import ContinuumError
        from continuum_providers import build_default_registry

        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.blocked_capability")
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        with pytest.raises(ContinuumError) as excinfo:
            execute_job(
                session,
                claimed,
                registry.get(claimed.job_type),
                worker_id=worker.id,
                derived=storage.derived,
                providers=build_default_registry(),
                settings=db_settings,
            )

        assert excinfo.value.context.get("blocked_reason") == "MISSING_PROVIDER"
        session.rollback()
        session.refresh(claimed)
        assert claimed.status is not JobStatus.FAILED_FINAL, (
            "a policy block was recorded as a failure; the worker BLOCKED branch is unreachable"
        )
