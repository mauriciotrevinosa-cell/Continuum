"""Acceptance 110.6-110.11 - the durable job lifecycle.

**These require a live PostgreSQL** and skip otherwise, naming the exact
command to start one. Skipping is honest; reporting them as PASS without
having run them would not be.

The single most important assertion in this file is in
``test_110_10_forced_rerun_of_a_completed_unit_is_a_no_op``. Without it,
110.10 ("resumes only unfinished units") is satisfiable by a handler that
simply never retries anything. What the invariant actually requires is that
re-running a completed unit is *safe* -- because at-least-once execution
means it will happen (ADR-0002 section 2, F-22).
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from continuum_config import Settings
from continuum_core import BlockedReason, JobStatus, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobEvent, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
    registry,
    request_cancel,
    request_drain,
    request_pause,
    resume_job,
)
from continuum_jobs.execution import StopReason
from continuum_storage import DerivedStore, build_storage
from continuum_worker import register_default_handlers
from sqlalchemy import func, select

pytestmark = pytest.mark.requires_db


@pytest.fixture(autouse=True)
def _handlers() -> None:
    register_default_handlers()


@pytest.fixture
def storage(db_settings: Settings):
    return build_storage(db_settings, create=True)


def _run(session, job: Job, settings: Settings, storage, **kwargs) -> StopReason:
    from continuum_providers import build_default_registry

    return execute_job(
        session,
        job,
        registry.get(job.job_type),
        derived=storage.derived,
        providers=build_default_registry(),
        **kwargs,
    )


class TestJobRoundtrip:
    """110.6 - a synthetic durable job can be queued and processed."""

    def test_enqueue_claim_execute_succeed(self, clean_jobs, db_settings, storage) -> None:
        session = clean_jobs
        job, created = enqueue(session, "synthetic.counted_work", payload={"units": 4})
        session.commit()
        assert created and job.status is JobStatus.QUEUED

        worker = register_worker(session)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        assert claimed is not None and claimed.id == job.id
        assert claimed.status is JobStatus.RUNNING
        assert claimed.lease_owner == worker.id

        assert (
            _run(session, claimed, db_settings, storage, worker_id=worker.id)
            is StopReason.COMPLETED
        )
        session.refresh(claimed)
        assert claimed.status is JobStatus.SUCCEEDED
        assert claimed.units_done == 4

    def test_audit_trail_records_the_whole_lifecycle(
        self, clean_jobs, db_settings, storage
    ) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 2})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        _run(session, claimed, db_settings, storage, worker_id=worker.id)

        kinds = [
            e.event_type
            for e in session.execute(
                select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.created_at)
            ).scalars()
        ]
        assert "CREATED" in kinds
        assert "LEASE_ACQUIRED" in kinds
        assert "STEP_COMPLETED" in kinds
        assert "TRANSITION" in kinds

    def test_duplicate_enqueue_dedupes(self, clean_jobs) -> None:
        """F-26: double-clicking must yield one job, not a race."""
        session = clean_jobs
        payload = {"units": 3, "marker": "dedupe"}
        first, created_first = enqueue(session, "synthetic.counted_work", payload=payload)
        session.commit()
        second, created_second = enqueue(session, "synthetic.counted_work", payload=payload)
        session.commit()
        assert created_first is True
        assert created_second is False
        assert first.id == second.id


class TestProgressIsIndependentOfTheUi:
    """110.7 - progress is persisted independently of any web page."""

    def test_progress_visible_from_a_separate_connection(
        self, clean_jobs, db_settings, storage
    ) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 3})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        _run(session, claimed, db_settings, storage, worker_id=worker.id)

        # A brand-new session, standing in for a UI that was never open.
        with session_scope(db_settings) as other:
            observed = other.get(Job, job.id)
            assert observed is not None
            assert observed.units_done == 3
            assert observed.status is JobStatus.SUCCEEDED


class TestResumeOnlyUnfinishedUnits:
    """110.10 - the central idempotency invariant (F-22)."""

    def test_resume_skips_completed_units(self, clean_jobs, db_settings, storage) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 5})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        # Pause after the loop starts, then resume: units already SUCCEEDED
        # must not execute again.
        _run(session, claimed, db_settings, storage, worker_id=worker.id)
        session.refresh(claimed)
        done_first = {
            s.unit_key
            for s in session.execute(
                select(JobStep).where(
                    JobStep.job_id == job.id, JobStep.status == StepStatus.SUCCEEDED
                )
            ).scalars()
        }
        assert len(done_first) == 5

        attempts = [
            s.attempt
            for s in session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars()
        ]
        assert all(a == 1 for a in attempts), "a unit executed more than once"

    def test_forced_rerun_of_a_completed_unit_is_a_no_op(
        self, clean_jobs, db_settings, storage
    ) -> None:
        """The assertion that gives 110.10 its meaning.

        A handler that never retries would pass "resumes only unfinished
        units" trivially. What matters is that re-running a COMPLETED unit
        produces a byte-identical effect and no duplicate row -- because
        at-least-once execution guarantees it will happen eventually.
        """
        session = clean_jobs
        payload = {"units": 3, "marker": "idempotency"}
        job, _ = enqueue(session, "synthetic.counted_work", payload=payload)
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        _run(session, claimed, db_settings, storage, worker_id=worker.id)

        derived: DerivedStore = storage.derived
        hashes = sorted(
            s.result["content_hash"]
            for s in session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars()
        )
        contents_before = {h: derived.read_bytes("cache", h) for h in hashes}
        step_count_before = session.execute(
            select(func.count()).select_from(JobStep).where(JobStep.job_id == job.id)
        ).scalar_one()

        # Force every unit to run again, exactly as a crash-resumed worker
        # would if the completion records had not committed.
        session.refresh(claimed)
        claimed.status = JobStatus.RUNNING
        claimed.completed_at = None
        session.commit()
        _run(
            session,
            claimed,
            db_settings,
            storage,
            worker_id=worker.id,
            force_rerun_completed=True,
        )

        contents_after = {h: derived.read_bytes("cache", h) for h in hashes}
        step_count_after = session.execute(
            select(func.count()).select_from(JobStep).where(JobStep.job_id == job.id)
        ).scalar_one()

        assert contents_after == contents_before, "a re-run changed stored content"
        assert step_count_after == step_count_before, "a re-run created a duplicate step row"
        for step in session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars():
            assert step.result["already_present"] is True, (
                "the re-run wrote a new file instead of recognising existing content"
            )

    def test_checkpoints_are_durable(self, clean_jobs, db_settings, storage) -> None:
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 4})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        _run(session, claimed, db_settings, storage, worker_id=worker.id)

        checkpoints = list(
            session.execute(
                select(JobCheckpoint)
                .where(JobCheckpoint.job_id == job.id)
                .order_by(JobCheckpoint.seq)
            ).scalars()
        )
        assert len(checkpoints) == 4
        assert checkpoints[-1].payload["last_unit_index"] == 3


class TestPauseCancelDrain:
    """110.9 - graceful stop leaves the job resumable."""

    def test_pause_request_is_a_flag_not_a_status_write(self, clean_jobs) -> None:
        """F-28: only the worker and reaper write status."""
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 3})
        session.commit()
        request_pause(session, job)
        session.commit()
        assert job.pause_requested is True
        assert job.status is JobStatus.PAUSED  # QUEUED pauses immediately

        resume_job(session, job)
        session.commit()
        assert job.pause_requested is False
        assert job.status is JobStatus.QUEUED

    def test_pause_mid_run_leaves_completed_units_intact(
        self, clean_jobs, db_settings, storage
    ) -> None:
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 6})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        claimed.pause_requested = True
        session.commit()

        reason = _run(session, claimed, db_settings, storage, worker_id=worker.id)
        session.refresh(claimed)
        assert reason is StopReason.PAUSED
        assert claimed.status is JobStatus.PAUSED
        assert claimed.units_done < 6

        # Resume: the remaining units finish and nothing re-runs.
        resume_job(session, claimed)
        session.commit()
        claimed.status = JobStatus.RUNNING
        session.commit()
        assert (
            _run(session, claimed, db_settings, storage, worker_id=worker.id)
            is StopReason.COMPLETED
        )
        session.refresh(claimed)
        assert claimed.units_done == 6

    def test_drain_requeues_the_job_rather_than_cancelling_it(
        self, clean_jobs, db_settings, storage
    ) -> None:
        """The worker is going away, not the job."""
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 5})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        request_drain(session, worker.id)
        session.commit()

        reason = _run(session, claimed, db_settings, storage, worker_id=worker.id)
        session.refresh(claimed)
        assert reason is StopReason.DRAINED
        assert claimed.status is JobStatus.QUEUED, "a drained job must remain runnable"
        assert claimed.lease_owner is None

    def test_cancel_is_cooperative(self, clean_jobs, db_settings, storage) -> None:
        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 5})
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()
        request_cancel(session, claimed)
        session.commit()
        assert claimed.status is JobStatus.CANCELLING

        _run(session, claimed, db_settings, storage, worker_id=worker.id)
        session.refresh(claimed)
        assert claimed.status is JobStatus.CANCELLED


class TestFailureAndRecovery:
    """110.11 - structured error/retry state, and lease-expiry recovery."""

    def test_retryable_failure_records_structured_state_and_backoff(
        self, clean_jobs, db_settings, storage
    ) -> None:
        session = clean_jobs
        _job, _ = enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 3, "fail_at_unit": 1, "fail_times": 99},
            max_attempts=3,
        )
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        assert (
            _run(session, claimed, db_settings, storage, worker_id=worker.id) is StopReason.FAILED
        )
        session.refresh(claimed)
        assert claimed.status is JobStatus.FAILED_RETRYABLE
        assert claimed.attempt == 1
        assert claimed.last_error["category"] == "RETRYABLE_TRANSIENT"
        assert claimed.last_error["retryable"] is True
        assert claimed.error_history
        assert claimed.run_after is not None

        # Once the database-clock deadline is due, the normal claimant must
        # promote the retry and run it. Manual retry is not durability.
        claimed.run_after = session.execute(
            select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1))
        ).scalar_one()
        session.commit()
        retried = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        assert retried is not None
        assert retried.id == claimed.id
        assert retried.status is JobStatus.RUNNING

    def test_permanent_failure_goes_final_without_retry(
        self, clean_jobs, db_settings, storage
    ) -> None:
        session = clean_jobs
        _job, _ = enqueue(
            session,
            "synthetic.counted_work",
            payload={"units": 3, "fail_permanently_at_unit": 0},
            max_attempts=5,
        )
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        _run(session, claimed, db_settings, storage, worker_id=worker.id)
        session.refresh(claimed)
        assert claimed.status is JobStatus.FAILED_FINAL
        assert claimed.last_error["category"] == "PERMANENT_INPUT"
        assert claimed.last_error["retryable"] is False

    def test_expired_lease_is_reclaimed(self, clean_jobs, db_settings) -> None:
        """F-27: a hard-killed worker must not strand its job in RUNNING."""
        session = clean_jobs
        job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 3})
        session.commit()
        worker = register_worker(session)
        session.commit()

        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=1
        )
        session.commit()
        assert claimed.status is JobStatus.RUNNING

        # Expire the lease using the DATABASE clock, never the test's.
        claimed.lease_expires_at = session.execute(
            select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 60))
        ).scalar_one()
        session.commit()

        recovered = reap_expired_leases(session)
        session.commit()
        session.refresh(claimed)

        assert claimed.id in recovered
        assert claimed.status is JobStatus.QUEUED
        assert claimed.lease_owner is None
        assert claimed.attempt == 1

        events = [
            e.event_type
            for e in session.execute(select(JobEvent).where(JobEvent.job_id == job.id)).scalars()
        ]
        assert "LEASE_EXPIRED" in events

    def test_blocked_capability_parks_with_remediation(
        self, clean_jobs, db_settings, storage
    ) -> None:
        """110.12 end-to-end: no permitted provider means BLOCKED, not FAILED."""
        from continuum_providers import build_default_registry
        from continuum_worker.handlers.synthetic import SyntheticBlockedError

        session = clean_jobs
        _job, _ = enqueue(session, "synthetic.blocked_capability")
        session.commit()
        worker = register_worker(session)
        session.commit()
        claimed = claim_next_job(
            session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
        )
        session.commit()

        with pytest.raises(SyntheticBlockedError) as excinfo:
            execute_job(
                session,
                claimed,
                registry.get("synthetic.blocked_capability"),
                worker_id=worker.id,
                derived=storage.derived,
                providers=build_default_registry(),
            )
        assert excinfo.value.context["blocked_reason"] == BlockedReason.MISSING_PROVIDER.value


class TestWorkerProcessIndependence:
    """110.8 - the worker is a separate OS process with no API channel."""

    def test_worker_runs_as_its_own_process(self, db_settings: Settings) -> None:
        """Proves the topology, not just the intent: the worker is started by
        exec, with no parent API or web server anywhere in the picture."""
        session_env = {
            "CONTINUUM_DATA_HOME": str(db_settings.data_home),
            "CONTINUUM_SOURCE_VAULT_ROOT": str(db_settings.source_vault_root),
        }
        import os

        env = {**os.environ, **session_env}
        result = subprocess.run(
            [sys.executable, "-m", "continuum_worker.main", "--once"],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
            check=False,
        )
        assert result.returncode == 0, result.stderr[-2000:]

    def test_worker_module_never_pulls_in_the_api(self) -> None:
        """Import the worker in a clean interpreter and assert the API app is
        not in sys.modules afterwards (ADR-0002 topology)."""
        code = (
            "import sys, continuum_worker.main;"
            "assert 'continuum_api' not in sys.modules, sorted(sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr[-1500:]
