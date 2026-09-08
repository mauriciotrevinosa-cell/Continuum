"""Cold final Phase 0 audit of the worker lifecycle at e29ee6e.

Audit evidence, not shipped acceptance coverage.

**Auditor independence is reduced.** The same model family implemented the
H-4/H-5/H-5b remediation under audit here. Every hypothesis below is therefore
reconstructed from the invariant rather than adapted from the shipped suites,
and every ownership handover goes through the **real** reaper and claim paths
(``reap_expired_leases`` then ``claim_next_job``) -- never a direct UPDATE that
fakes a final state. That reduces the correlation; it does not remove it.

**The invariant.** A worker that no longer owns the current RUNNING lease must
not mutate durable state and must not continue acting as the executor of that
job. Ownership validation and the mutation must be one PostgreSQL
serialization unit.

**Lifecycle boundaries probed.** claim, handler resolution, plan, materialise
plan, pre-unit ownership, step start, effect start, effect heartbeat,
exception, BLOCKED, completion/checkpoint/progress, lease renewal, final
transition.

Interleavings are forced with threading events and by polling for a
*condition* (a lock-blocked backend in ``pg_stat_activity``), never by sleeping
on a guess.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, ClassVar

import pytest
from continuum_config import Settings
from continuum_core import BlockedReason, JobStatus, StepStatus
from continuum_db.models import Job, JobCheckpoint, JobStep
from continuum_db.session import session_scope
from continuum_jobs import (
    OwnershipLostError,
    block_job,
    claim_next_job,
    enqueue,
    execute_job,
    fail_job,
    reap_expired_leases,
    register_worker,
    registry,
    request_drain,
    transition,
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec
from sqlalchemy import func, select, text, update

pytest_plugins = ["tests.conftest"]
pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Independent scaffolding
# ---------------------------------------------------------------------------


class _Handler:
    """A handler whose plan and unit phases can each be suspended."""

    job_type: ClassVar[str] = "audit.cold"

    def __init__(
        self,
        *,
        plan_gate: tuple[threading.Event, threading.Event] | None = None,
        unit_gate: tuple[threading.Event, threading.Event] | None = None,
        raise_in_plan: bool = False,
        raise_in_unit: bool = False,
        dirty_session: bool = False,
        units: int = 1,
        settings: Settings | None = None,
    ) -> None:
        self.plan_gate = plan_gate
        self.unit_gate = unit_gate
        self.raise_in_plan = raise_in_plan
        self.raise_in_unit = raise_in_unit
        self.dirty_session = dirty_session
        self.units = units
        self.settings = settings
        self.plans = 0
        self.units_executed = 0
        #: Durable ``lease_owner`` read by the handler at the instant the
        #: effect begins. This is the decisive H-6 evidence: it is the job's
        #: own record of who owned it while this effect was running.
        self.owner_at_effect_start: list[uuid.UUID | None] = []

    def plan(self, ctx: Any) -> list[UnitSpec]:
        self.plans += 1
        if self.dirty_session:
            # An adversarial planner: leave uncommitted ORM state behind.
            ctx.session.add(
                JobCheckpoint(job_id=ctx.job_id, seq=9999, payload={"planner": "side effect"})
            )
        if self.plan_gate is not None:
            entered, release = self.plan_gate
            entered.set()
            assert release.wait(60), "plan gate never released"
        if self.raise_in_plan:
            raise RuntimeError("deterministic planning failure")
        return [UnitSpec(f"unit-{i}") for i in range(self.units)]

    def execute_unit(self, ctx: Any, _unit: UnitSpec) -> UnitOutcome:
        self.units_executed += 1
        if self.settings is not None:
            with session_scope(self.settings) as s:
                self.owner_at_effect_start.append(
                    s.execute(select(Job.lease_owner).where(Job.id == ctx.job_id)).scalar_one()
                )
        if self.unit_gate is not None:
            entered, release = self.unit_gate
            entered.set()
            assert release.wait(60), "unit gate never released"
        if self.raise_in_unit:
            raise RuntimeError("deterministic unit failure")
        return UnitOutcome(result={"landed": True}, checkpoint={"at": "unit"})


def _prepare(
    session, *, job_type: str = _Handler.job_type, lease_seconds: int = 30
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    enqueue(session, job_type, payload={"case": str(uuid.uuid4())})
    worker_a = register_worker(session)
    worker_b = register_worker(session)
    session.commit()
    claimed = claim_next_job(
        session, worker_id=worker_a.id, resource_classes=["cpu"], lease_seconds=lease_seconds
    )
    session.commit()
    assert claimed is not None
    return claimed.id, worker_a.id, worker_b.id


def _expire(settings: Settings, job_id: uuid.UUID) -> None:
    """Push the lease into the past. Ownership itself is left untouched."""
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


def _steal(settings: Settings, job_id: uuid.UUID, worker_b: uuid.UUID) -> None:
    """Hand ownership to B through the genuine reaper and claim paths.

    Expiry and reap share one transaction so a heartbeat renewing on its own
    connection cannot slip between them and renew the lease being expired.
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
            "blocked_reason": job.blocked_reason,
            "steps": steps,
            "checkpoints": checkpoints,
        }


def _run_worker(
    settings: Settings, job_id: uuid.UUID, worker_id: uuid.UUID, handler: Any, **kwargs: Any
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


def _await_contention(settings: Settings, done: threading.Event, timeout: float = 30.0) -> str:
    """Wait until a concurrent writer is provably blocked, or until it finishes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if done.is_set():
            return "finished"
        if _blocked_backends(settings) > 0:
            return "blocked"
        time.sleep(0.02)
    return "timeout"


# ---------------------------------------------------------------------------
# H-1 / H-2 / H-3 reconstructed
# ---------------------------------------------------------------------------


def test_h1_stale_worker_cannot_finalize_or_write_after_reclaim(clean_jobs, db_settings) -> None:
    """Boundary: completion / checkpoint / progress / final transition."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(entered, release))

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _snapshot(db_settings, job_id) == baseline, (
        "H-1: a stale worker mutated the new owner's job after reclaim"
    )


def test_h2_stale_worker_exception_records_nothing(clean_jobs, db_settings) -> None:
    """Boundary: unit exception after ownership transfer."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(entered, release), raise_in_unit=True)

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]

    after = _snapshot(db_settings, job_id)
    assert after == baseline, f"H-2: failure state was written.\nbefore={baseline}\nafter={after}"
    assert after["last_error"] is None
    assert after["error_history"] == []


def test_h3_every_transition_path_requires_ownership(clean_jobs, db_settings) -> None:
    """Boundary: every durable status writer, exercised directly."""
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        for target in (JobStatus.SUCCEEDED, JobStatus.PAUSING, JobStatus.CANCELLING):
            with pytest.raises(OwnershipLostError):
                transition(s, job, target, worker_id=worker_a)
            s.rollback()

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        with pytest.raises(OwnershipLostError):
            fail_job(s, job, _as_structured(), worker_id=worker_a)
        s.rollback()

    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        with pytest.raises(OwnershipLostError):
            block_job(s, job, BlockedReason.MISSING_PROVIDER, {"message": "x"}, worker_id=worker_a)
        s.rollback()

    assert _snapshot(db_settings, job_id) == baseline


def _as_structured():
    from continuum_jobs.execution import _structured

    return _structured(RuntimeError("stale failure from a worker that lost the lease"))


# ---------------------------------------------------------------------------
# H-4 — pre-unit ownership / step start
# ---------------------------------------------------------------------------


def test_h4_preunit_proof_and_step_write_are_one_serialization_unit(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """A reclaim cannot enter the interval between the proof and the write."""
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs)
    in_window, release_window = threading.Event(), threading.Event()
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def hooked(session, job, worker_id):
        result = real_stop(session, job, worker_id)
        if result is None and job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            in_window.set()
            assert release_window.wait(60)
        return result

    monkeypatch.setattr(execution, "_stop_requested", hooked)

    unit_entered, unit_release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(unit_entered, unit_release))
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert in_window.wait(30), "the pre-unit window was never reached"

    stolen = threading.Event()

    def steal() -> None:
        try:
            _steal(db_settings, job_id, worker_b)
        finally:
            stolen.set()

    threading.Thread(target=steal, daemon=True).start()
    outcome = _await_contention(db_settings, stolen)

    assert outcome == "blocked", (
        f"H-4: a reclaim entered the pre-unit window instead of blocking ({outcome})"
    )
    assert not stolen.is_set()

    release_window.set()
    assert stolen.wait(30)

    with session_scope(db_settings) as s:
        step = s.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        assert step.attempt == 1, "the step was started more than once"

    unit_release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]


def test_h4_worker_already_stale_writes_no_step_state(clean_jobs, db_settings, monkeypatch) -> None:
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs)
    at_check, release_check = threading.Event(), threading.Event()
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def hooked(session, job, worker_id):
        if job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            at_check.set()
            assert release_check.wait(60)
        return real_stop(session, job, worker_id)

    monkeypatch.setattr(execution, "_stop_requested", hooked)

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, _Handler(), lease_seconds=30, heartbeat_seconds=0.1
    )
    assert at_check.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["steps"] == [("unit-0", StepStatus.PENDING, 0, False)]

    release_check.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == []
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert _snapshot(db_settings, job_id) == baseline


# ---------------------------------------------------------------------------
# H-5 / H-5b — planning
# ---------------------------------------------------------------------------


def _plan_then_steal(clean_jobs, db_settings, **kw) -> tuple[dict, dict, list, list]:
    job_id, worker_a, worker_b = _prepare(clean_jobs)
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(plan_gate=(entered, release), units=3, **kw)

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert entered.wait(30)
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    release.set()
    thread.join(60)
    assert not thread.is_alive()
    return baseline, _snapshot(db_settings, job_id), outcomes, errors


def test_h5_stale_planner_writes_no_steps_and_no_units_total(clean_jobs, db_settings) -> None:
    baseline, after, outcomes, errors = _plan_then_steal(clean_jobs, db_settings)
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert after["steps"] == []
    assert after["units_total"] is None
    assert after == baseline


def test_h5b_planning_exception_after_loss_does_not_escape(clean_jobs, db_settings) -> None:
    baseline, after, outcomes, errors = _plan_then_steal(
        clean_jobs, db_settings, raise_in_plan=True
    )
    assert errors == [], (
        f"H-5b: {type(errors[0]).__name__ if errors else ''} escaped execute_job: {errors}"
    )
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert after == baseline


def test_planner_session_side_effects_do_not_survive_ownership_loss(
    clean_jobs, db_settings
) -> None:
    """``lock_job_row`` flushes pending state BEFORE proving ownership.

    A planner that leaves uncommitted ORM state behind therefore has that
    state pushed to the database before ``assert_owner`` runs. The claim is
    that the rollback on the ownership-loss path discards it. That is asserted
    here adversarially rather than believed.
    """
    baseline, after, outcomes, errors = _plan_then_steal(
        clean_jobs, db_settings, dirty_session=True
    )
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert after["checkpoints"] == 0, (
        f"a planner's pending session state became durable after ownership "
        f"transfer: {after['checkpoints']} checkpoint(s)"
    )
    assert after == baseline


# ---------------------------------------------------------------------------
# H-6 — the start-of-effect lease gap
# ---------------------------------------------------------------------------


def test_h6_expired_lease_owner_executes_effect_after_reclaim(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """H-6: owner-with-expired-lease passes the pre-unit check and runs anyway.

    ``_stop_requested`` validates ``lease_owner`` and ``status`` but not
    ``lease_expires_at > now()``. A worker whose lease has expired -- after an
    OS stall or a GC pause longer than the lease -- is therefore still
    accepted, commits the step start, and only then starts the heartbeat. The
    first beat is one interval away, and during that gap the reaper may
    legitimately reclaim.

    The handler records the durable ``lease_owner`` at the instant its effect
    begins. That single value settles the question: if it is B, then A ran the
    effect while B was the recorded executor.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs, lease_seconds=30)

    # 1. A is still the owner, but its lease is now expired. Ownership is not
    #    touched; only the deadline moves.
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def expire_then_check(session, job, worker_id):
        if job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            _expire(db_settings, job_id)
        return real_stop(session, job, worker_id)

    monkeypatch.setattr(execution, "_stop_requested", expire_then_check)

    # 3. Pause A after the step-start commit, before the effect heartbeat.
    at_effect_start, release_effect = threading.Event(), threading.Event()
    real_beat = execution.LeaseHeartbeat
    entries = {"n": 0}

    class _GatedHeartbeat(real_beat):  # type: ignore[valid-type,misc]
        def __enter__(self):
            entries["n"] += 1
            # The first construction is the planning heartbeat; the second is
            # the effect heartbeat, which is the boundary under test.
            if entries["n"] == 2:
                at_effect_start.set()
                assert release_effect.wait(60)
            return super().__enter__()

    monkeypatch.setattr(execution, "LeaseHeartbeat", _GatedHeartbeat)

    handler = _Handler(settings=db_settings)
    thread, _outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert at_effect_start.wait(30), "the effect-start boundary was never reached"

    with session_scope(db_settings) as s:
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.lease_owner == worker_a, "A should still be the recorded owner here"
        expired_now = s.execute(select(func.now() > Job.lease_expires_at).where(Job.id == job_id))
        assert expired_now.scalar_one() is True, "A's lease should be expired at this point"
        step = s.execute(select(JobStep).where(JobStep.job_id == job_id)).scalar_one()
        assert step.status is StepStatus.RUNNING, "the step start should already be committed"

    # 4. The real reaper reclaims and B claims.
    _steal(db_settings, job_id, worker_b)
    after_steal = _snapshot(db_settings, job_id)
    assert after_steal["owner"] == worker_b

    # 5. Resume A.
    release_effect.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"

    # 6. Did A execute the effect while B was the durable owner?
    assert handler.owner_at_effect_start != [worker_b], (
        "H-6 DEFECT: the stale worker executed the unit effect while worker B "
        f"was the recorded owner (owner seen at effect start: "
        f"{handler.owner_at_effect_start}); a synchronous owner-scoped lease "
        "renewal before the effect is required for exclusivity"
    )
    assert handler.units_executed == 0, (
        "H-6 DEFECT: the stale worker ran the effect after ownership transfer"
    )


def test_h6_expired_lease_owner_writes_no_durable_completion(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """Separates the two halves of H-6: durable writes vs effect execution.

    Even if the effect runs, the completion record must not land. This isolates
    whether the damage is duplicated compute only, or durable corruption too.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs, lease_seconds=30)
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def expire_then_check(session, job, worker_id):
        if job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            _expire(db_settings, job_id)
        return real_stop(session, job, worker_id)

    monkeypatch.setattr(execution, "_stop_requested", expire_then_check)

    at_effect_start, release_effect = threading.Event(), threading.Event()
    real_beat = execution.LeaseHeartbeat
    entries = {"n": 0}

    class _GatedHeartbeat(real_beat):  # type: ignore[valid-type,misc]
        def __enter__(self):
            entries["n"] += 1
            if entries["n"] == 2:
                at_effect_start.set()
                assert release_effect.wait(60)
            return super().__enter__()

    monkeypatch.setattr(execution, "LeaseHeartbeat", _GatedHeartbeat)

    handler = _Handler(settings=db_settings)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert at_effect_start.wait(30)

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)

    release_effect.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]

    after = _snapshot(db_settings, job_id)
    assert after == baseline, (
        f"a worker with an expired lease wrote durable completion state after "
        f"the reclaim.\nbefore={baseline}\nafter={after}"
    )


# ---------------------------------------------------------------------------
# H-7 / H-7b — the BLOCKED paths, through the REAL worker loop
# ---------------------------------------------------------------------------


class _GatedBlockedHandler:
    """Raises a genuine blocked_reason error, on demand, after a gate."""

    job_type: ClassVar[str] = "audit.blocked_gate"

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def plan(self, _ctx: Any) -> list[UnitSpec]:
        return [UnitSpec("probe")]

    def execute_unit(self, _ctx: Any, _unit: UnitSpec) -> UnitOutcome:
        self.entered.set()
        assert self.release.wait(60)
        from continuum_worker.handlers.synthetic import SyntheticBlockedError

        raise SyntheticBlockedError(
            "No permitted provider for this capability.",
            technical_detail="audit H-7",
            remediation="Install a provider.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )


def _build_worker(db_settings: Settings):
    from continuum_worker.main import Worker

    worker = Worker(db_settings)
    worker.register()
    return worker


def test_h7_blocked_exception_after_ownership_loss_through_worker_loop(
    clean_jobs, db_settings
) -> None:
    """H-7: the BLOCKED re-raise runs BEFORE the ownership-loss logic.

    ``execute_job`` re-raises any ``ContinuumError`` carrying a
    ``blocked_reason`` before it consults ownership at all. ``run_once`` then
    catches ``SyntheticBlockedError`` and calls ``block_job(..., worker_id=A)``,
    which under default-on ownership raises ``OwnershipLostError``. Nothing in
    ``run_once`` or ``run_forever`` catches that.
    """
    handler = _GatedBlockedHandler()
    if handler.job_type not in registry.known_types():
        registry.register(handler)
    else:  # pragma: no cover - re-registration across runs
        registry.register(handler)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    with session_scope(db_settings) as s:
        worker_b = register_worker(s).id

    errors: list[BaseException] = []
    finished = threading.Event()

    def run() -> None:
        try:
            worker_a.run_once()
        # Deliberately BaseException: an escape kills the worker loop.
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True).start()
    assert handler.entered.wait(30), "the unit never started"

    with session_scope(db_settings) as s:
        job_id = s.execute(select(Job.id).where(Job.job_type == handler.job_type)).scalar_one()
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    handler.release.set()
    assert finished.wait(60), "run_once never returned"

    # Durable state first, so a crash finding does not hide a corruption
    # finding: they are separate questions with separate severities.
    assert _snapshot(db_settings, job_id) == baseline, (
        "H-7 DEFECT: a stale worker wrote BLOCKED state onto the new owner's job"
    )
    assert errors == [], (
        f"H-7 DEFECT: {type(errors[0]).__name__ if errors else ''} escaped "
        f"Worker.run_once() and would terminate run_forever(): {errors}"
    )


def test_h7b_unknown_handler_blocked_path_after_ownership_loss(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """H-7b: claim -> UnknownJobTypeError -> block_job, with a handover between.

    The pause sits between the claim and the BLOCKED mutation. A stale worker
    must not overwrite B, and must not take the worker process down.
    """
    import importlib

    # ``continuum_worker/__init__`` binds the *function* ``main``, which
    # shadows the submodule of the same name for attribute access. Go
    # through importlib to get the real module object.
    worker_main = importlib.import_module("continuum_worker.main")

    unknown_type = f"audit.unknown.{uuid.uuid4().hex[:8]}"
    with session_scope(db_settings) as s:
        enqueue(s, unknown_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    with session_scope(db_settings) as s:
        worker_b = register_worker(s).id

    at_block, release_block = threading.Event(), threading.Event()
    real_block_job = worker_main.block_job

    def gated_block_job(*args: Any, **kwargs: Any):
        at_block.set()
        assert release_block.wait(60)
        return real_block_job(*args, **kwargs)

    monkeypatch.setattr(worker_main, "block_job", gated_block_job)

    errors: list[BaseException] = []
    finished = threading.Event()

    def run() -> None:
        try:
            worker_a.run_once()
        # Deliberately BaseException: an escape kills the worker loop.
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True).start()
    assert at_block.wait(30), "the BLOCKED mutation was never reached"

    with session_scope(db_settings) as s:
        job_id = s.execute(select(Job.id).where(Job.job_type == unknown_type)).scalar_one()
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release_block.set()
    assert finished.wait(60), "run_once never returned"

    # Durable state first, so a crash finding does not hide a corruption
    # finding: they are separate questions with separate severities.
    assert _snapshot(db_settings, job_id) == baseline, (
        "H-7b DEFECT: a stale worker overwrote the new owner's job with BLOCKED"
    )
    assert errors == [], (
        f"H-7b DEFECT: {type(errors[0]).__name__ if errors else ''} escaped "
        f"Worker.run_once() and would terminate run_forever(): {errors}"
    )


# ---------------------------------------------------------------------------
# Lock / deadlock regression probes
# ---------------------------------------------------------------------------


def _hold_preunit_window(monkeypatch, job_id: uuid.UUID):
    """Suspend a worker inside the pre-unit window, holding the row lock."""
    import continuum_jobs.execution as execution

    in_window, release_window = threading.Event(), threading.Event()
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def hooked(session, job, worker_id):
        result = real_stop(session, job, worker_id)
        if result is None and job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            in_window.set()
            assert release_window.wait(60)
        return result

    monkeypatch.setattr(execution, "_stop_requested", hooked)
    return in_window, release_window


def test_api_pause_flag_while_worker_holds_preunit_lock(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """A pause request must not deadlock against the pre-unit lock."""
    job_id, worker_a, _worker_b = _prepare(clean_jobs)
    in_window, release_window = _hold_preunit_window(monkeypatch, job_id)

    handler = _Handler(units=2)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert in_window.wait(30)

    flagged = threading.Event()

    def set_pause() -> None:
        try:
            with session_scope(db_settings) as s:
                s.execute(update(Job).where(Job.id == job_id).values(pause_requested=True))
        finally:
            flagged.set()

    threading.Thread(target=set_pause, daemon=True).start()
    release_window.set()

    assert flagged.wait(30), "the pause flag write never completed (possible deadlock)"
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.PAUSED], f"pause was not honoured: {outcomes}"

    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.PAUSED
    assert after["owner"] is None


def test_drain_while_worker_holds_preunit_lock(clean_jobs, db_settings, monkeypatch) -> None:
    """A drain request must not deadlock against the pre-unit lock."""
    job_id, worker_a, _worker_b = _prepare(clean_jobs)
    in_window, release_window = _hold_preunit_window(monkeypatch, job_id)

    handler = _Handler(units=2)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert in_window.wait(30)

    drained = threading.Event()

    def ask_drain() -> None:
        try:
            with session_scope(db_settings) as s:
                request_drain(s, worker_a)
        finally:
            drained.set()

    threading.Thread(target=ask_drain, daemon=True).start()
    release_window.set()

    assert drained.wait(30), "the drain request never completed (possible deadlock)"
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised: {errors}"
    assert outcomes == [StopReason.DRAINED], f"drain was not honoured: {outcomes}"

    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.QUEUED, "a drained job must return to the queue"
    assert after["owner"] is None


def test_no_deadlock_between_heartbeat_reaper_and_preunit_lock(clean_jobs, db_settings) -> None:
    """Concurrent reaper passes against a live worker must not deadlock."""
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)
    handler = _Handler(units=4)

    stop = threading.Event()
    reaper_errors: list[BaseException] = []

    def reap_loop() -> None:
        while not stop.is_set():
            try:
                with session_scope(db_settings) as s:
                    reap_expired_leases(s)
            except BaseException as exc:  # a deadlock would surface here
                reaper_errors.append(exc)
                return

    threading.Thread(target=reap_loop, daemon=True).start()

    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.05
    )
    thread.join(60)
    stop.set()

    assert not thread.is_alive()
    assert errors == [], f"execute_job raised under concurrent reaping: {errors}"
    assert reaper_errors == [], f"the reaper failed under contention: {reaper_errors}"
    assert outcomes == [StopReason.COMPLETED]

    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.SUCCEEDED
    assert after["units_done"] == 4


def test_rightful_owner_completes_the_whole_lifecycle(clean_jobs, db_settings) -> None:
    """The guards must not cost the ordinary path anything."""
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
    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.SUCCEEDED
    assert after["units_total"] == 3
    assert after["units_done"] == 3
    assert all(s[1] is StepStatus.SUCCEEDED for s in after["steps"])  # type: ignore[union-attr]
    assert all(s[2] == 1 for s in after["steps"])  # type: ignore[union-attr]


def test_planning_failure_while_still_owner_still_fails(clean_jobs, db_settings) -> None:
    """Ownership dominance must not swallow genuine planning failures."""
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
# Test-reliability finding: the shipped _steal helper has a renewable gap
# ---------------------------------------------------------------------------


def test_expired_lease_is_renewable_by_its_previous_owner(clean_jobs, db_settings) -> None:
    """An expired lease can be renewed back to life by the worker that held it.

    ``renew_lease`` filters on ``status = RUNNING AND lease_owner = :worker``
    and deliberately does **not** require ``lease_expires_at > now()``. Until
    the reaper actually reclaims, the previous owner is still the owner, so
    the renewal is accepted.

    That is a defensible design decision -- reaping, not the clock, is what
    transfers ownership -- but it has two consequences worth recording:

    1. it is the mechanism behind H-6, since a worker with a dead lease keeps
       behaving as the executor until something reclaims the job; and
    2. it makes any test helper that expires a lease in one transaction and
       reaps in a *separate* one racy against a live heartbeat.
    """
    from continuum_jobs import renew_lease

    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)

    _expire(db_settings, job_id)
    with session_scope(db_settings) as s:
        assert (
            s.execute(
                select(func.now() > Job.lease_expires_at).where(Job.id == job_id)
            ).scalar_one()
            is True
        )

    # Exactly one heartbeat beat landing in the gap.
    with session_scope(db_settings) as s:
        renewed = renew_lease(s, job_id, 300, worker_id=worker_a)
    assert renewed is True, "an expired lease was not renewable by its previous owner"

    # The reaper now finds nothing: the steal would fail from here.
    with session_scope(db_settings) as s:
        assert reap_expired_leases(s) == [], (
            "the reaper reclaimed a lease that had just been renewed"
        )
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.lease_owner == worker_a
        assert row.status is JobStatus.RUNNING
