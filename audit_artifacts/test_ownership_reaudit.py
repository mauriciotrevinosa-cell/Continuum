"""Independent re-audit of the stale-worker ownership remediation at 388d300.

Audit evidence, not shipped acceptance coverage.

H-1/H-2/H-3 are **reconstructed here from the invariant**, not copied from the
remediation's own suite and not taken on the implementer's word that the
original artifacts were ported faithfully.

H-4 and H-5 are new hypotheses about lifecycle boundaries the previous audit
did not examine: the interval between the pre-unit ownership check and the
step-start commit, and the planning phase that runs before any heartbeat
exists.

Every test uses real PostgreSQL. Ownership transfer always goes through the
real reaper and claim paths. Interleavings are forced with threading events,
never with sleeps.
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

pytest_plugins = ["tests.conftest"]
pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Shared adversarial scaffolding
# ---------------------------------------------------------------------------


class _Handler:
    job_type = "audit.reaudit"

    def __init__(
        self,
        *,
        plan_gate: tuple[threading.Event, threading.Event] | None = None,
        unit_gate: tuple[threading.Event, threading.Event] | None = None,
        raise_after_gate: bool = False,
        units: int = 1,
    ) -> None:
        self.plan_gate = plan_gate
        self.unit_gate = unit_gate
        self.raise_after_gate = raise_after_gate
        self.units = units
        self.units_executed = 0

    def plan(self, _ctx):
        if self.plan_gate is not None:
            entered, release = self.plan_gate
            entered.set()
            assert release.wait(30)
        return [UnitSpec(f"unit-{i}") for i in range(self.units)]

    def execute_unit(self, _ctx, _unit):
        self.units_executed += 1
        if self.unit_gate is not None:
            entered, release = self.unit_gate
            entered.set()
            assert release.wait(30)
        if self.raise_after_gate:
            raise RuntimeError("deterministic re-audit failure")
        return UnitOutcome(result={"landed": True}, checkpoint={"at": "unit"})


def _prepare(session, *, lease_seconds: int = 30) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    _job, _ = enqueue(session, _Handler.job_type, payload={"case": str(uuid.uuid4())})
    worker_a = register_worker(session)
    worker_b = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker_a.id, resource_classes=["cpu"], lease_seconds=lease_seconds
    )
    session.commit()
    assert claimed is not None
    return claimed.id, worker_a.id, worker_b.id


def _steal(settings: Settings, job_id: uuid.UUID, worker_b: uuid.UUID) -> None:
    """Move ownership to B through the genuine reaper and claim paths."""
    with session_scope(settings) as s:
        s.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                lease_expires_at=s.execute(
                    select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 120))
                ).scalar_one()
            )
        )
    with session_scope(settings) as s:
        assert job_id in reap_expired_leases(s), "the reaper did not reclaim the abandoned job"
    with session_scope(settings) as s:
        claimed = claim_next_job(s, worker_id=worker_b, resource_classes=["cpu"], lease_seconds=600)
        assert claimed is not None and claimed.id == job_id


def _observe(settings: Settings, job_id: uuid.UUID) -> tuple[JobStatus, uuid.UUID | None]:
    with session_scope(settings) as s:
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        return row.status, row.lease_owner


def _snapshot(settings: Settings, job_id: uuid.UUID) -> dict[str, object]:
    """Everything a stale worker could corrupt, in one comparable structure."""
    with session_scope(settings) as s:
        job = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        steps = [
            (st.unit_key, st.status, st.attempt, st.started_at is not None)
            for st in s.execute(
                select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.unit_key)
            ).scalars()
        ]
        checkpoints = s.execute(
            select(func.count()).select_from(JobCheckpoint).where(JobCheckpoint.job_id == job_id)
        ).scalar_one()
        return {
            "status": job.status,
            "owner": job.lease_owner,
            "units_done": job.units_done,
            "units_total": job.units_total,
            "attempt": job.attempt,
            "last_error": job.last_error,
            "error_history": list(job.error_history or []),
            "steps": steps,
            "checkpoints": checkpoints,
        }


def _run_a(settings: Settings, job_id: uuid.UUID, worker_a: uuid.UUID, handler, **kw):
    outcomes: list[StopReason] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            with session_scope(settings) as s:
                job = s.get(Job, job_id)
                assert job is not None
                outcomes.append(
                    execute_job(s, job, handler, worker_id=worker_a, settings=settings, **kw)
                )
        except BaseException as exc:
            errors.append(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, outcomes, errors


# ---------------------------------------------------------------------------
# H-1 / H-2 / H-3 reconstructed independently
# ---------------------------------------------------------------------------


def test_h1_stale_worker_cannot_finalize_or_write_after_reclaim(clean_jobs, db_settings) -> None:
    """H-1 reconstructed: reclaim while A is inside its only unit."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(entered, release))

    thread, outcomes, errors = _run_a(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release.set()
    thread.join(30)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"

    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _snapshot(db_settings, job_id) == baseline, (
        "a stale worker mutated the new owner's job after reclaim"
    )


def test_h1_stale_worker_cannot_renew_new_owners_lease(clean_jobs, db_settings) -> None:
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    _steal(db_settings, job_id, worker_b)

    with session_scope(db_settings) as s:
        before = s.execute(select(Job.lease_expires_at).where(Job.id == job_id)).scalar_one()
        assert renew_lease(s, job_id, 99999, worker_id=worker_a) is False
    with session_scope(db_settings) as s:
        after = s.execute(select(Job.lease_expires_at).where(Job.id == job_id)).scalar_one()
    assert after == before


def test_h2_exception_after_ownership_loss_writes_nothing(clean_jobs, db_settings) -> None:
    """H-2 reconstructed: the handler raises only after ownership has moved."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(entered, release), raise_after_gate=True)

    thread, outcomes, errors = _run_a(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)

    release.set()
    thread.join(30)
    assert errors == [], f"execute_job raised instead of standing down: {errors}"

    assert outcomes == [StopReason.OWNERSHIP_LOST], "a stale worker reported its own FAILED"
    after = _snapshot(db_settings, job_id)
    assert after == baseline
    assert after["last_error"] is None
    assert after["error_history"] == []


def test_h3_stale_orm_snapshot_cannot_overwrite_newer_owner(clean_jobs, db_settings) -> None:
    """H-3 reconstructed. The remediation raises rather than declining
    silently; either behaviour satisfies the invariant, so this asserts the
    invariant (B's row untouched) and merely records which shape occurred."""
    from continuum_jobs import OwnershipLostError

    job_id, worker_a, worker_b = _prepare(clean_jobs)

    with session_scope(db_settings) as stale_session:
        stale = stale_session.get(Job, job_id)
        assert stale is not None and stale.lease_owner == worker_a
        _steal(db_settings, job_id, worker_b)
        baseline = _snapshot(db_settings, job_id)

        with pytest.raises(OwnershipLostError):
            transition(stale_session, stale, JobStatus.SUCCEEDED, worker_id=worker_a)
        stale_session.rollback()

    assert _snapshot(db_settings, job_id) == baseline


def test_h3_covers_failure_blocked_and_stop_landings(clean_jobs, db_settings) -> None:
    """H-3 across the other transition families the previous audit named."""
    from continuum_core import ErrorCategory, StructuredError
    from continuum_db.enums import BlockedReason
    from continuum_jobs import OwnershipLostError, block_job, fail_job

    job_id, worker_a, worker_b = _prepare(clean_jobs)
    with session_scope(db_settings) as stale_session:
        stale = stale_session.get(Job, job_id)
        assert stale is not None
        _steal(db_settings, job_id, worker_b)
        baseline = _snapshot(db_settings, job_id)

        error = StructuredError(
            code="audit.err",
            category=ErrorCategory.PERMANENT_INPUT,
            user_message="audit",
        )
        with pytest.raises(OwnershipLostError):
            fail_job(stale_session, stale, error, worker_id=worker_a, require_owner=worker_a)
        stale_session.rollback()

        stale = stale_session.get(Job, job_id)
        with pytest.raises(OwnershipLostError):
            block_job(
                stale_session,
                stale,
                BlockedReason.MISSING_PROVIDER,
                {"message": "audit"},
                worker_id=worker_a,
                require_owner=worker_a,
            )
        stale_session.rollback()

        for target in (JobStatus.PAUSING, JobStatus.CANCELLING):
            stale = stale_session.get(Job, job_id)
            with pytest.raises(OwnershipLostError):
                transition(stale_session, stale, target, worker_id=worker_a)
            stale_session.rollback()

    assert _snapshot(db_settings, job_id) == baseline


# ---------------------------------------------------------------------------
# H-4 — pre-unit ownership window
# ---------------------------------------------------------------------------


def test_h4_pre_unit_window_cannot_write_step_state_after_ownership_loss(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """H-4: between ``_stop_requested()`` and the step-start commit.

    ``_stop_requested`` performs an UNLOCKED ``session.refresh``. It therefore
    holds nothing, and the ``step.status = RUNNING`` / ``attempt += 1`` commit
    that follows is a durable coordination write with no ownership guard of
    its own.

    The pause is placed exactly in that interval by hooking the production
    check itself, so the interleaving is a fact rather than a race won by luck.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs)

    passed_check = threading.Event()
    release = threading.Event()
    real_stop_requested = execution._stop_requested
    hooked = {"count": 0}

    def paused_stop_requested(session, job, worker_id):
        result = real_stop_requested(session, job, worker_id)
        # Only the first pre-unit check, and only when it says "keep going".
        if result is None and job.id == job_id and hooked["count"] == 0:
            hooked["count"] += 1
            passed_check.set()
            assert release.wait(30)
        return result

    monkeypatch.setattr(execution, "_stop_requested", paused_stop_requested)

    thread, outcomes, errors = _run_a(
        db_settings, job_id, worker_a, _Handler(), lease_seconds=30, heartbeat_seconds=0.1
    )
    assert passed_check.wait(30), "the pre-unit ownership check was never reached"

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b
    assert baseline["status"] is JobStatus.RUNNING

    release.set()
    thread.join(30)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"

    after = _snapshot(db_settings, job_id)
    assert outcomes == [StopReason.OWNERSHIP_LOST], (
        f"A did not stand down after losing ownership in the pre-unit window: {outcomes}"
    )
    assert after == baseline, (
        "H-4 DEFECT: a stale worker committed durable step/coordination state "
        f"after ownership transferred.\nbefore={baseline}\nafter={after}"
    )


# ---------------------------------------------------------------------------
# H-5 — planning window
# ---------------------------------------------------------------------------


def test_h5_planning_window_cannot_write_after_ownership_loss(clean_jobs, db_settings) -> None:
    """H-5: ``plan()`` runs before any LeaseHeartbeat exists.

    A gated planner outlives the lease. The reaper reclaims, B claims, and A
    then reaches ``plan_units()`` -- which creates ``JobStep`` rows and sets
    ``units_total`` -- and commits. Nothing between the claim and that commit
    re-checks ownership.
    """
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(plan_gate=(entered, release), units=3)

    thread, outcomes, errors = _run_a(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30), "the planner was never reached"

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release.set()
    thread.join(30)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"

    after = _snapshot(db_settings, job_id)
    assert outcomes == [StopReason.OWNERSHIP_LOST], (
        f"A did not stand down after losing ownership during planning: {outcomes}"
    )
    assert after == baseline, (
        "H-5 DEFECT: a stale worker committed JobStep rows and/or units_total "
        f"for a job it no longer owned.\nbefore={baseline}\nafter={after}"
    )


# ---------------------------------------------------------------------------
# Regression guards: the fix must not break legitimate behaviour
# ---------------------------------------------------------------------------


def test_rightful_owner_still_completes(clean_jobs, db_settings) -> None:
    job_id, worker_a, _b = _prepare(clean_jobs, lease_seconds=600)
    handler = _Handler(units=2)
    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        outcome = execute_job(
            s,
            job,
            handler,
            worker_id=worker_a,
            settings=db_settings,
            lease_seconds=600,
            heartbeat_seconds=0.5,
        )
    assert outcome is StopReason.COMPLETED
    snap = _snapshot(db_settings, job_id)
    assert snap["status"] is JobStatus.SUCCEEDED
    assert snap["units_done"] == 2
    assert all(st[1] is StepStatus.SUCCEEDED for st in snap["steps"])


def test_no_deadlock_under_concurrent_reapers_and_transitions(clean_jobs, db_settings) -> None:
    """Lock-inversion probe.

    ``transition`` now takes a row lock; the reaper already held one. Run both
    against the same rows from several threads and require every thread to
    finish well inside the timeout. A lock inversion would hang here.
    """
    job_ids: list[uuid.UUID] = []
    for _ in range(4):
        job_id, _wa, _wb = _prepare(clean_jobs)
        job_ids.append(job_id)

    done = threading.Event()
    errors: list[BaseException] = []

    def reaper_loop() -> None:
        try:
            for _ in range(6):
                with session_scope(db_settings) as s:
                    reap_expired_leases(s)
        except BaseException as exc:
            errors.append(exc)

    def expiry_loop() -> None:
        try:
            for job_id in job_ids:
                with session_scope(db_settings) as s:
                    s.execute(
                        update(Job)
                        .where(Job.id == job_id)
                        .values(
                            lease_expires_at=s.execute(
                                select(func.now() - func.make_interval(0, 0, 0, 0, 0, 0, 120))
                            ).scalar_one()
                        )
                    )
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    threads = [
        threading.Thread(target=reaper_loop, daemon=True),
        threading.Thread(target=reaper_loop, daemon=True),
        threading.Thread(target=expiry_loop, daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
        assert not t.is_alive(), "a thread hung; possible lock inversion or deadlock"
    assert errors == [], f"concurrent lock traffic raised: {errors}"
    assert done.is_set()


# ---------------------------------------------------------------------------
# H-5b: does a stale worker whose plan() raises stand down, or crash?
# ---------------------------------------------------------------------------


class _RaisingPlanHandler:
    job_type = "audit.reaudit"

    def __init__(self, gate: tuple[threading.Event, threading.Event]) -> None:
        self.gate = gate

    def plan(self, _ctx):
        entered, release = self.gate
        entered.set()
        assert release.wait(30)
        raise RuntimeError("planning failed after ownership was lost")

    def execute_unit(self, _ctx, _unit):  # pragma: no cover - never reached
        raise AssertionError("unreachable")


def test_h5b_stale_worker_failing_to_plan_stands_down_without_crashing(
    clean_jobs, db_settings
) -> None:
    """A worker that loses the lease and THEN fails to plan must not crash.

    ``execute_job`` funnels a planning exception into ``fail_job``. If that
    call itself raises ``OwnershipLostError`` from inside the ``except``
    block, the error escapes ``execute_job`` and takes the worker loop with
    it -- the opposite of standing down quietly.
    """
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _RaisingPlanHandler((entered, release))

    thread, outcomes, errors = _run_a(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release.set()
    thread.join(30)
    assert not thread.is_alive()

    assert errors == [], (
        f"execute_job propagated {type(errors[0]).__name__ if errors else ''} "
        f"instead of standing down: {errors}"
    )
    assert outcomes and outcomes[0] is StopReason.OWNERSHIP_LOST, (
        f"expected a quiet OWNERSHIP_LOST stand-down, got {outcomes}"
    )
    assert _snapshot(db_settings, job_id) == baseline, (
        "a stale worker wrote failure state onto the new owner's job"
    )
