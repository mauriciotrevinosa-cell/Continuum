"""Pre-unit and planning ownership suite — re-audit H-4, H-5, H-5b.

**The invariant, unchanged.** No worker may mutate durable job coordination,
progress or final status after it no longer owns the current RUNNING lease.
Ownership validation and the mutation are one PostgreSQL serialization unit.

**The three defects this pins down.**

* **H-4** — the pre-unit check used an unlocked ``session.refresh()``. It
  proved ownership at an instant and then let go, leaving three statements of
  window before the step-start commit. A reclaimed lease in that window let a
  stale worker stamp ``status``, ``started_at`` and ``attempt`` on the
  rightful owner's step row.
* **H-5** — planning ran with no lease maintenance and no ownership re-check,
  so a slow ``plan()`` was *expected* to outlive its lease. The stale planner
  then created ``JobStep`` rows and set ``units_total`` on another worker's
  job -- damage that outlived the moment, because ``plan_units`` skips
  existing unit keys and only ever grows ``units_total``.
* **H-5b** — a planning exception after ownership loss reached ``fail_job``,
  which then raised ``OwnershipLostError`` from inside the ``except`` block.
  Nothing in the worker loop or ``run_forever`` catches it, so a routine race
  killed the worker process.

**How H-4 is tested, and why it reads inverted.** The fix holds the job row
lock from the ownership proof through the step-start commit. A test that
"steals the lease inside the window" therefore cannot exist any more: the
steal is precisely what the lock prevents. So the window test asserts the
serialization directly -- a concurrent reclaim attempt is observed *blocked on
a lock* in ``pg_stat_activity`` while the worker sits inside the window, and
is still incomplete at the moment the worker is released. Before the fix that
reclaim completed immediately and nothing blocked.

Synchronisation is by threading primitives and by polling for a *condition*
(a blocked backend, a database clock passing a deadline), never by sleeping on
a guess.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
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
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec
from sqlalchemy import func, select, text, update

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


class _Handler:
    """A handler whose planning and unit phases can each be suspended."""

    job_type = "test.preunit"

    def __init__(
        self,
        *,
        plan_gate: tuple[threading.Event, threading.Event] | None = None,
        unit_gate: tuple[threading.Event, threading.Event] | None = None,
        raise_in_plan: bool = False,
        units: int = 1,
    ) -> None:
        self.plan_gate = plan_gate
        self.unit_gate = unit_gate
        self.raise_in_plan = raise_in_plan
        self.units = units
        self.plans = 0
        self.units_executed = 0

    def plan(self, _ctx: object) -> list[UnitSpec]:
        self.plans += 1
        if self.plan_gate is not None:
            entered, release = self.plan_gate
            entered.set()
            assert release.wait(60), "plan gate was never released"
        if self.raise_in_plan:
            raise RuntimeError("deterministic planning failure")
        return [UnitSpec(f"unit-{i}") for i in range(self.units)]

    def execute_unit(self, _ctx: object, _unit: UnitSpec) -> UnitOutcome:
        self.units_executed += 1
        if self.unit_gate is not None:
            entered, release = self.unit_gate
            entered.set()
            assert release.wait(60), "unit gate was never released"
        return UnitOutcome(result={"landed": True}, checkpoint={"at": "unit"})


def _prepare(session, *, lease_seconds: int = 30) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Enqueue a job, register two workers, and let A claim it."""
    enqueue(session, _Handler.job_type, payload={"case": str(uuid.uuid4())})
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
    """Move ownership to B through the genuine reaper and claim paths.

    Expiry and reap share **one** transaction. A heartbeat renewing on its own
    connection would otherwise be free to slip between them and renew the very
    lease this is expiring, making the handover a race rather than a fact.
    """
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
        assert job_id in reap_expired_leases(s), "the reaper did not reclaim the abandoned job"
    with session_scope(settings) as s:
        claimed = claim_next_job(s, worker_id=worker_b, resource_classes=["cpu"], lease_seconds=600)
        assert claimed is not None and claimed.id == job_id


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


def _run_worker(
    settings: Settings, job_id: uuid.UUID, worker_id: uuid.UUID, handler: _Handler, **kwargs: object
) -> tuple[threading.Thread, list[StopReason], list[BaseException]]:
    outcomes: list[StopReason] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            with session_scope(settings) as s:
                job = s.get(Job, job_id)
                assert job is not None
                outcomes.append(
                    execute_job(s, job, handler, worker_id=worker_id, settings=settings, **kwargs)
                )
        # Deliberately BaseException: an escape is exactly what is under test.
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcomes, errors


def _blocked_backends(settings: Settings) -> int:
    """How many backends are currently waiting on a lock in this database."""
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


def _await_lock_contention(settings: Settings, done: threading.Event, timeout: float = 30.0) -> str:
    """Wait until the reclaim is *provably blocked*, or until it finishes.

    Returns which happened. Discriminating between the two is the whole test:
    "blocked" means the ownership proof and the step write are one
    serialization unit; "finished" means a reclaim slipped into the window,
    which is the H-4 defect.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if done.is_set():
            return "finished"
        if _blocked_backends(settings) > 0:
            return "blocked"
        time.sleep(0.02)
    return "timeout"


# ---------------------------------------------------------------------------
# H-4 — the pre-unit window
# ---------------------------------------------------------------------------


def test_h4_reclaim_cannot_enter_the_preunit_window(clean_jobs, db_settings, monkeypatch) -> None:
    """The ownership proof and the step-start write are one serialization unit.

    A worker is suspended in the exact interval between the pre-unit check and
    the step-start commit. A concurrent reclaim -- forced expiry followed by
    the real reaper -- is then observed *blocked on a lock*, and is still
    incomplete when the worker is released. Before the fix nothing was held
    across that interval, so the reclaim completed immediately.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs)

    in_window = threading.Event()
    release_window = threading.Event()
    real_stop_requested = execution._stop_requested
    seen = {"count": 0}

    def paused_stop_requested(session, job, worker_id):
        result = real_stop_requested(session, job, worker_id)
        # Only the first pre-unit check, and only when it says "keep going":
        # that is precisely the window, with the row lock still held.
        if result is None and job.id == job_id and seen["count"] == 0:
            seen["count"] += 1
            in_window.set()
            assert release_window.wait(60), "window gate was never released"
        return result

    monkeypatch.setattr(execution, "_stop_requested", paused_stop_requested)

    unit_entered, unit_release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(unit_entered, unit_release))
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert in_window.wait(30), "the pre-unit window was never reached"

    stolen = threading.Event()
    steal_errors: list[BaseException] = []

    def steal() -> None:
        try:
            _steal(db_settings, job_id, worker_b)
        except BaseException as exc:
            steal_errors.append(exc)
        finally:
            stolen.set()

    steal_thread = threading.Thread(target=steal, daemon=True)
    steal_thread.start()

    outcome = _await_lock_contention(db_settings, stolen)
    assert outcome == "blocked", (
        "H-4 REGRESSION: a reclaim entered the pre-unit window instead of "
        f"blocking on the job row lock (observed: {outcome})"
    )
    assert not stolen.is_set(), "the reclaim completed while the worker held the window"

    release_window.set()

    # The step was written by the rightful owner, under the lock, before the
    # reclaim was ever allowed to proceed.
    assert stolen.wait(30), "the reclaim never completed after the window closed"
    assert steal_errors == [], f"the reclaim itself failed: {steal_errors}"

    with session_scope(db_settings) as s:
        step = s.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        assert step.attempt == 1, "the step was started more than once"
        assert step.started_at is not None

    after_steal = _snapshot(db_settings, job_id)
    assert after_steal["owner"] == worker_b

    unit_release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _snapshot(db_settings, job_id) == after_steal, (
        "the stale worker mutated the new owner's job after the handover"
    )


def test_h4_stale_worker_cannot_mutate_step_status_started_at_or_attempt(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """A worker that lost the lease before the check writes no step state.

    The reclaim happens *before* the pre-unit check runs, so the check is
    reached by a worker that is already stale. It must stand down leaving
    ``status``, ``started_at`` and ``attempt`` exactly as it found them.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs)

    at_check = threading.Event()
    release_check = threading.Event()
    real_stop_requested = execution._stop_requested
    seen = {"count": 0}

    def paused_stop_requested(session, job, worker_id):
        # Pause BEFORE the real check, so the handover lands first.
        if job.id == job_id and seen["count"] == 0:
            seen["count"] += 1
            at_check.set()
            assert release_check.wait(60), "check gate was never released"
        return real_stop_requested(session, job, worker_id)

    monkeypatch.setattr(execution, "_stop_requested", paused_stop_requested)

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, _Handler(), lease_seconds=30, heartbeat_seconds=0.1
    )
    assert at_check.wait(30), "the pre-unit check was never reached"

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b
    assert baseline["steps"] == [("unit-0", StepStatus.PENDING, 0, False)]

    release_check.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]

    after = _snapshot(db_settings, job_id)
    assert after["steps"] == [("unit-0", StepStatus.PENDING, 0, False)], (
        "H-4 REGRESSION: a stale worker wrote step status, started_at or attempt"
    )
    assert after == baseline


# ---------------------------------------------------------------------------
# H-5 — the planning window
# ---------------------------------------------------------------------------


def _plan_then_lose_ownership(
    clean_jobs, db_settings, *, raise_in_plan: bool = False, units: int = 3
) -> tuple[dict[str, object], dict[str, object], list[StopReason], list[BaseException]]:
    """Suspend a worker inside ``plan()``, hand the job to B, then release."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(plan_gate=(entered, release), raise_in_plan=raise_in_plan, units=units)

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30), "planning was never reached"

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    return baseline, _snapshot(db_settings, job_id), outcomes, errors


def test_h5_ownership_loss_during_slow_planning_stands_down(clean_jobs, db_settings) -> None:
    """Losing the lease while planning is a stand-down, not a write."""
    baseline, after, outcomes, errors = _plan_then_lose_ownership(clean_jobs, db_settings)

    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert after == baseline, (
        f"H-5 REGRESSION: a stale planner mutated the new owner's job.\n"
        f"before={baseline}\nafter={after}"
    )


def test_h5_stale_planner_cannot_create_steps(clean_jobs, db_settings) -> None:
    """No ``JobStep`` row may be created by a planner that lost the lease."""
    baseline, after, _outcomes, _errors = _plan_then_lose_ownership(clean_jobs, db_settings)

    assert baseline["steps"] == []
    assert after["steps"] == [], (
        f"H-5 REGRESSION: a stale planner created step rows: {after['steps']}"
    )


def test_h5_stale_planner_cannot_change_units_total(clean_jobs, db_settings) -> None:
    """``units_total`` is progress state and is off-limits to a stale planner."""
    baseline, after, _outcomes, _errors = _plan_then_lose_ownership(clean_jobs, db_settings)

    assert baseline["units_total"] is None
    assert after["units_total"] is None, (
        f"H-5 REGRESSION: a stale planner set units_total to {after['units_total']}"
    )


# ---------------------------------------------------------------------------
# H-5b — a planning exception raised after ownership was lost
# ---------------------------------------------------------------------------


def test_h5b_planning_exception_after_ownership_loss_returns_ownership_lost(
    clean_jobs, db_settings
) -> None:
    """Ownership loss dominates the planning failure, and nothing escapes.

    ``fail_job`` inside the planning ``except`` block raises
    ``OwnershipLostError`` when the lease is gone. Nothing in the worker loop
    or ``run_forever`` catches that, so before the fix this killed the worker
    process. The stand-down belongs here, in ``execute_job``.
    """
    baseline, after, outcomes, errors = _plan_then_lose_ownership(
        clean_jobs, db_settings, raise_in_plan=True
    )

    assert errors == [], (
        f"H-5b REGRESSION: {type(errors[0]).__name__ if errors else ''} escaped "
        f"execute_job and would have killed the worker: {errors}"
    )
    assert outcomes == [StopReason.OWNERSHIP_LOST], f"expected a quiet stand-down, got {outcomes}"
    assert after == baseline, (
        f"H-5b REGRESSION: a stale planner recorded failure state on the new "
        f"owner's job.\nbefore={baseline}\nafter={after}"
    )
    assert after["last_error"] is None
    assert after["error_history"] == []
    assert after["status"] is JobStatus.RUNNING


def test_planning_exception_while_still_owner_still_fails_the_job(clean_jobs, db_settings) -> None:
    """The stand-down must not swallow genuine planning failures.

    Ownership dominating the exception is only correct while ownership is
    actually lost. A planner that still owns its job and raises must fail it
    exactly as before, or H-5b's fix would silently discard real errors.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs)
    handler = _Handler(raise_in_plan=True)

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        reason = execute_job(
            s, job, handler, worker_id=worker_a, settings=db_settings, lease_seconds=30
        )

    assert reason is StopReason.FAILED
    after = _snapshot(db_settings, job_id)
    assert after["status"] in {JobStatus.FAILED_RETRYABLE, JobStatus.FAILED_FINAL}
    assert after["last_error"] is not None


# ---------------------------------------------------------------------------
# The heartbeat half of the H-5 fix
# ---------------------------------------------------------------------------


def test_long_planning_retains_the_lease_via_heartbeat(clean_jobs, db_settings) -> None:
    """A slow but honest planner keeps the lease it legitimately holds.

    The lock closes the race; the heartbeat is what stops the race from being
    the *expected* outcome. With a two-second lease and a plan held well past
    it, the reaper must find nothing to reclaim and the job must still be
    owned by its planner.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=2)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(plan_gate=(entered, release), units=2)

    with session_scope(db_settings) as s:
        original_expiry = s.execute(
            select(Job.lease_expires_at).where(Job.id == job_id)
        ).scalar_one()
    assert original_expiry is not None

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=2, heartbeat_seconds=0.2
    )
    assert entered.wait(30), "planning was never reached"

    # Wait for the database clock to pass the ORIGINAL deadline. Without a
    # heartbeat the lease is expired by definition at this point.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        with session_scope(db_settings) as s:
            if bool(s.execute(select(func.now() > original_expiry)).scalar_one()):
                break
        time.sleep(0.05)
    else:  # pragma: no cover - only on a pathologically slow machine
        pytest.fail("the database clock never passed the original lease deadline")

    with session_scope(db_settings) as s:
        assert reap_expired_leases(s) == [], (
            "the reaper reclaimed a job whose planner was still heartbeating"
        )
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.lease_owner == worker_a, "the planner lost its lease during a long plan"
        assert row.status is JobStatus.RUNNING
        assert row.lease_expires_at is not None
        assert row.lease_expires_at > original_expiry, "the lease was never renewed"

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.COMPLETED]


def test_rightful_owner_plans_and_executes_normally(clean_jobs, db_settings) -> None:
    """The guards must not cost the ordinary path anything.

    Every assertion above is about what a *stale* worker may not do. This one
    proves the owner still does all of it: plans, materialises its steps, runs
    them, records progress and finishes.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs)
    handler = _Handler(units=3)

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        reason = execute_job(
            s,
            job,
            handler,
            worker_id=worker_a,
            settings=db_settings,
            lease_seconds=30,
            heartbeat_seconds=0.1,
        )

    assert reason is StopReason.COMPLETED
    assert handler.plans == 1
    assert handler.units_executed == 3

    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.SUCCEEDED
    assert after["units_total"] == 3
    assert after["units_done"] == 3
    assert after["checkpoints"] == 3
    assert [s[0] for s in after["steps"]] == ["unit-0", "unit-1", "unit-2"]  # type: ignore[union-attr]
    assert all(s[1] is StepStatus.SUCCEEDED for s in after["steps"])  # type: ignore[union-attr]
    assert all(s[2] == 1 for s in after["steps"]), "a unit was started more than once"  # type: ignore[union-attr]

    with session_scope(db_settings) as s:
        step = s.execute(select(JobStep).where(JobStep.job_id == job_id)).scalars().first()
        assert step is not None
        assert step.started_at is not None
        assert step.completed_at is not None
        assert step.completed_at >= step.started_at
        assert isinstance(step.started_at, dt.datetime)
