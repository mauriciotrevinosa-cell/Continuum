"""Second-audit-only adversarial PostgreSQL concurrency probes.

These tests intentionally describe required invariants and are expected to
fail on candidate 9629a729. They are not product regression tests and do not
modify production code.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

import continuum_jobs.queue as queue_module
from continuum_config import WRITABLE_ROOT_KEYS
from continuum_db.enums import JobStatus, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    add_dependency,
    claim_next_job,
    enqueue,
    reap_expired_leases,
    register_worker,
)
from continuum_storage import DerivedStore
from sqlalchemy import func, select

pytest_plugins = ["tests.conftest"]


def test_real_process_death_after_effect_recovers_without_duplicate(
    clean_jobs, db_settings
) -> None:
    session = clean_jobs
    job, _ = enqueue(
        session,
        "synthetic.counted_work",
        payload={"units": 1, "die_at_unit": 0, "marker": "audit-real-hard-death"},
    )
    session.commit()
    job_id = job.id
    env = {
        **os.environ,
        "CONTINUUM_DATA_HOME": str(db_settings.data_home),
        "CONTINUUM_SOURCE_VAULT_ROOT": str(db_settings.source_vault_root),
    }

    killed = subprocess.run(
        [sys.executable, "-m", "continuum_worker.main", "--once"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert killed.returncode != 0

    session.expire_all()
    interrupted = session.get(Job, job_id)
    assert interrupted is not None and interrupted.status is JobStatus.RUNNING
    step = session.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
    assert step.status is StepStatus.RUNNING
    checkpoints = session.execute(
        select(func.count()).select_from(JobCheckpoint).where(JobCheckpoint.job_id == job_id)
    ).scalar_one()
    assert checkpoints == 0
    interrupted.lease_expires_at = session.execute(
        select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 1))
    ).scalar_one()
    session.commit()

    with session_scope(db_settings) as reaper_session:
        assert job_id in reap_expired_leases(reaper_session)

    replacement = subprocess.run(
        [sys.executable, "-m", "continuum_worker.main", "--once"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert replacement.returncode == 0, replacement.stderr

    session.expire_all()
    recovered = session.get(Job, job_id)
    assert recovered is not None and recovered.status is JobStatus.SUCCEEDED
    steps = list(session.execute(select(JobStep).where(JobStep.job_id == job_id)).scalars())
    assert len(steps) == 1
    assert steps[0].attempt == 2
    assert steps[0].result is not None and steps[0].result["already_present"] is True
    digest = steps[0].result["content_hash"]
    subprocess_store = DerivedStore({key: db_settings.root(key) for key in WRITABLE_ROOT_KEYS})
    assert subprocess_store.verify("cache", digest)


def test_fresh_heartbeat_cannot_be_overwritten_by_stale_reaper_snapshot(
    clean_jobs, db_settings
) -> None:
    session = clean_jobs
    job, _ = enqueue(session, "synthetic.counted_work", payload={"units": 1})
    worker = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker.id, resource_classes=["cpu"], lease_seconds=30
    )
    assert claimed is not None
    claimed.lease_expires_at = session.execute(
        select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 30))
    ).scalar_one()
    session.commit()

    # Hold the row lock while writing a fresh heartbeat. The reaper's unlocked
    # SELECT sees the previously committed stale lease, then blocks only when
    # it tries to flush its stale decision.
    blocker = queue_module.Session(bind=session.get_bind(), expire_on_commit=False)
    live = blocker.execute(select(Job).where(Job.id == job.id).with_for_update()).scalar_one()
    live.lease_expires_at = blocker.execute(
        select(func.now() + func.make_interval(0, 0, 0, 0, 0, 0, 60))
    ).scalar_one()
    blocker.flush()

    finished = threading.Event()

    def reap() -> None:
        with session_scope(db_settings) as reaper_session:
            reap_expired_leases(reaper_session)
        finished.set()

    thread = threading.Thread(target=reap)
    thread.start()
    time.sleep(0.5)
    assert not finished.is_set(), "probe did not reach the intended blocked-update race"
    blocker.commit()
    blocker.close()
    thread.join(timeout=10)
    assert finished.is_set()

    session.expire_all()
    observed = session.get(Job, job.id)
    assert observed is not None
    assert observed.status is JobStatus.RUNNING, (
        "the reaper overwrote a fresh heartbeat using a stale pre-heartbeat snapshot"
    )
    assert observed.lease_owner == worker.id


def test_concurrent_opposing_dependency_edges_cannot_form_cycle(
    clean_jobs, db_settings, monkeypatch
) -> None:
    session = clean_jobs
    a, _ = enqueue(session, "synthetic.counted_work", payload={"marker": "audit-cycle-a"})
    b, _ = enqueue(session, "synthetic.counted_work", payload={"marker": "audit-cycle-b"})
    session.commit()

    original = queue_module._creates_cycle
    checked = threading.Barrier(2)

    def synchronized_check(*args, **kwargs):
        result = original(*args, **kwargs)
        checked.wait(timeout=10)
        return result

    monkeypatch.setattr(queue_module, "_creates_cycle", synchronized_check)
    errors: list[BaseException] = []

    def add(job_id, dependency_id) -> None:
        try:
            with session_scope(db_settings) as concurrent_session:
                add_dependency(concurrent_session, job_id, dependency_id)
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=add, args=(a.id, b.id))
    second = threading.Thread(target=add, args=(b.id, a.id))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    assert errors, "both opposing edges committed; concurrent transactions formed a cycle"
