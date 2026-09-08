"""Effect-start and BLOCKED ownership suite — cold audit H-6, H-7, H-7b.

**The invariant.** A worker that no longer owns the current RUNNING lease must
not mutate durable state **and must not continue acting as the executor of
that job**. Ownership validation and mutation are one PostgreSQL
serialization unit.

The second clause is what H-6 turned on. Prior suites proved a stale worker
could not *write*; none proved it could not *run*.

**The three defects pinned down here.**

* **H-6** — the pre-unit check validated ``lease_owner`` and ``status`` but
  not ``lease_expires_at``, so a worker stalled past its lease was still
  accepted. It committed the step start, released the row lock, and only then
  entered ``LeaseHeartbeat`` — whose first beat is a whole interval away. The
  reaper could legitimately reclaim in that gap, and the audit proved the
  first worker then began the effect anyway, with the job durably owned by
  someone else.
* **H-7** — the ``blocked_reason`` re-raise in ``execute_job`` sat *above* the
  ownership-dominance block, so a stale worker's provider block propagated
  into ``Worker.run_once()``, which called ``block_job`` for a job it no
  longer owned; that raised ``OwnershipLostError``, which nothing catches.
* **H-7b** — the same crash on the unknown-handler path, which never enters
  ``execute_job`` at all.

**The three layers of the H-6 fix, and what each test proves.**

1. ``_stop_requested`` refuses to *start* a unit on a lapsed lease, judged by
   the **database** clock (ADR-0002 section 5).
2. ``_authorize_effect`` performs a synchronous owner-scoped renewal **while
   the row lock is still held**, committed together with the step start. This
   is the actual guarantee: the reaper takes ``FOR UPDATE SKIP LOCKED`` and
   cannot interleave.
3. A non-locking ownership probe immediately before the effect, catching a
   stall between the authorising commit and the effect's first instruction.

Synchronisation is by threading events and by polling for a *condition*,
never by sleeping on a guess.
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
    claim_next_job,
    enqueue,
    execute_job,
    reap_expired_leases,
    register_worker,
    registry,
    renew_lease,
)
from continuum_jobs.execution import StopReason, UnitOutcome, UnitSpec
from sqlalchemy import func, select, text, update

pytestmark = pytest.mark.requires_db


# ---------------------------------------------------------------------------
# Scaffolding
# ---------------------------------------------------------------------------


class _Handler:
    """Records the durable owner at the instant each effect begins."""

    job_type: ClassVar[str] = "test.effect_start"

    def __init__(
        self,
        *,
        unit_gate: tuple[threading.Event, threading.Event] | None = None,
        units: int = 1,
        settings: Settings | None = None,
    ) -> None:
        self.unit_gate = unit_gate
        self.units = units
        self.settings = settings
        self.units_executed = 0
        self.owner_at_effect_start: list[uuid.UUID | None] = []
        self.lease_alive_at_effect_start: list[bool] = []

    def plan(self, _ctx: Any) -> list[UnitSpec]:
        return [UnitSpec(f"unit-{i}") for i in range(self.units)]

    def execute_unit(self, ctx: Any, _unit: UnitSpec) -> UnitOutcome:
        self.units_executed += 1
        if self.settings is not None:
            with session_scope(self.settings) as s:
                row = s.execute(
                    select(Job.lease_owner, Job.lease_expires_at > func.now()).where(
                        Job.id == ctx.job_id
                    )
                ).one()
                self.owner_at_effect_start.append(row[0])
                self.lease_alive_at_effect_start.append(bool(row[1]))
        if self.unit_gate is not None:
            entered, release = self.unit_gate
            entered.set()
            assert release.wait(60), "unit gate never released"
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

    Expiry and reap share one transaction (cold audit F-A): split across two,
    a heartbeat beat can renew the very lease being expired, because
    ``renew_lease`` deliberately carries no expiry predicate.
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
    # Claiming uses FOR UPDATE SKIP LOCKED, so a single attempt can legitimately
    # come back empty while another transaction is touching the row -- a beat
    # from the outgoing worker's heartbeat, for instance. Production claims in
    # a poll loop for exactly this reason, so a test that demands the first
    # attempt win is asserting something the system never promised. The
    # invariant asserted here is unchanged: B *does* take ownership.
    deadline = time.monotonic() + 30
    while True:
        with session_scope(settings) as s:
            claimed = claim_next_job(
                s, worker_id=worker_b, resource_classes=["cpu"], lease_seconds=600
            )
            if claimed is not None:
                assert claimed.id == job_id
                return
        assert time.monotonic() < deadline, "worker B never managed to claim the reaped job"


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
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if done.is_set():
            return "finished"
        if _blocked_backends(settings) > 0:
            return "blocked"
        time.sleep(0.02)
    return "timeout"


# ---------------------------------------------------------------------------
# H-6 layer 1 — a lapsed lease may not START a unit
# ---------------------------------------------------------------------------


def test_expired_lease_owner_may_not_begin_an_effect(clean_jobs, db_settings, monkeypatch) -> None:
    """Required coverage 1. The worker is still the recorded owner; its lease
    is not. Being named as owner is a statement about the past."""
    import continuum_jobs.execution as execution

    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)
    real_stop = execution._stop_requested
    seen = {"n": 0}

    def expire_then_check(session, job, worker_id):
        if job.id == job_id and seen["n"] == 0:
            seen["n"] += 1
            _expire(db_settings, job_id)
        return real_stop(session, job, worker_id)

    monkeypatch.setattr(execution, "_stop_requested", expire_then_check)

    handler = _Handler(settings=db_settings)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    thread.join(60)

    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]
    assert handler.units_executed == 0, "an effect began on a lapsed lease"

    # Planning ran while the lease was still alive, so the step row exists.
    # What must not have happened is the step being STARTED.
    after = _snapshot(db_settings, job_id)
    assert after["steps"] == [("unit-0", StepStatus.PENDING, 0, False)], (
        "a lapsed-lease worker wrote step state"
    )
    assert after["owner"] == worker_a, "the job is left for the reaper, not silently released"
    assert after["status"] is JobStatus.RUNNING


def test_expired_lease_check_uses_the_database_clock(clean_jobs, db_settings) -> None:
    """Required coverage 1. ADR-0002 section 5: the database clock decides.

    A worker's local clock is never consulted, so skew between machines can
    neither expire a live lease nor revive a dead one.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)
    _expire(db_settings, job_id)

    with session_scope(db_settings) as s:
        # The expiry is a fact about the database's own clock, not the
        # worker's: the comparison is evaluated server-side.
        expired = s.execute(
            select(func.now() > Job.lease_expires_at).where(Job.id == job_id)
        ).scalar_one()
        assert expired is True
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.lease_owner == worker_a, "still the recorded owner"
        assert row.status is JobStatus.RUNNING

    handler = _Handler(settings=db_settings)
    with session_scope(db_settings) as s:
        job = s.get(Job, job_id)
        assert job is not None
        reason = execute_job(
            s, job, handler, worker_id=worker_a, settings=db_settings, lease_seconds=30
        )

    assert reason is StopReason.OWNERSHIP_LOST
    assert handler.units_executed == 0


# ---------------------------------------------------------------------------
# H-6 layer 2 — synchronous owner-scoped renewal under the row lock
# ---------------------------------------------------------------------------


def test_lease_is_synchronously_renewed_before_the_effect_runs(clean_jobs, db_settings) -> None:
    """Required coverage 2 and 5.

    The renewal is not the heartbeat's first beat -- that is a whole interval
    away. It happens in the transaction that authorises the step, so the
    effect starts with a lease good for the full ``lease_seconds``.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)

    with session_scope(db_settings) as s:
        claim_expiry = s.execute(select(Job.lease_expires_at).where(Job.id == job_id)).scalar_one()
    assert claim_expiry is not None

    # A heartbeat interval long enough that no beat can fire during the unit:
    # whatever renewal the effect sees must be the synchronous one.
    entered, release = threading.Event(), threading.Event()
    handler = _Handler(unit_gate=(entered, release), settings=db_settings)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=600
    )
    assert entered.wait(30), "the effect never started"

    with session_scope(db_settings) as s:
        renewed_expiry = s.execute(
            select(Job.lease_expires_at).where(Job.id == job_id)
        ).scalar_one()
    assert renewed_expiry is not None
    assert renewed_expiry > claim_expiry, (
        "the lease was not synchronously renewed before the effect began"
    )
    assert handler.lease_alive_at_effect_start == [True]
    assert handler.owner_at_effect_start == [worker_a]

    release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == []
    assert outcomes == [StopReason.COMPLETED]


def test_reaper_cannot_reclaim_inside_the_authorized_effect_start_window(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """Required coverage 3.

    The ownership proof, the lease renewal and the step-start write are one
    serialization unit. A concurrent reclaim is observed *blocked on a lock*
    and is still incomplete when the worker is released.
    """
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
    handler = _Handler(unit_gate=(unit_entered, unit_release), settings=db_settings)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert in_window.wait(30), "the authorised window was never reached"

    stolen = threading.Event()

    def steal() -> None:
        try:
            _steal(db_settings, job_id, worker_b)
        finally:
            stolen.set()

    threading.Thread(target=steal, daemon=True).start()
    outcome = _await_contention(db_settings, stolen)

    assert outcome == "blocked", (
        f"a reclaim entered the authorised effect-start window instead of "
        f"blocking on the job row lock (observed: {outcome})"
    )
    assert not stolen.is_set()

    release_window.set()
    assert stolen.wait(30), "the reclaim never completed after the window closed"

    unit_release.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == []
    assert outcomes == [StopReason.OWNERSHIP_LOST]


# ---------------------------------------------------------------------------
# H-6 layer 3 — the effect does not begin once ownership is gone
# ---------------------------------------------------------------------------


def test_stale_worker_cannot_execute_the_effect_after_transfer(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """Required coverage 4.

    Layers 1 and 2 make this unreachable in production: the job leaves the
    authorising commit with a full lease and a running heartbeat. The pause
    below stands in for a stall between that commit and the effect's first
    instruction -- the same hazard, one step later.
    """
    import continuum_jobs.execution as execution

    job_id, worker_a, worker_b = _prepare(clean_jobs, lease_seconds=30)

    at_effect_start, release_effect = threading.Event(), threading.Event()
    real_beat = execution.LeaseHeartbeat
    entries = {"n": 0}

    class _GatedHeartbeat(real_beat):  # type: ignore[valid-type,misc]
        def __enter__(self):
            entries["n"] += 1
            # 1 is the planning heartbeat; 2 is the effect heartbeat.
            if entries["n"] == 2:
                at_effect_start.set()
                assert release_effect.wait(60)
            return super().__enter__()

    monkeypatch.setattr(execution, "LeaseHeartbeat", _GatedHeartbeat)

    handler = _Handler(settings=db_settings)
    thread, outcomes, errors = _run_worker(
        db_settings, job_id, worker_a, handler, lease_seconds=30, heartbeat_seconds=0.1
    )
    assert at_effect_start.wait(30), "the effect-start boundary was never reached"

    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release_effect.set()
    thread.join(60)
    assert not thread.is_alive()
    assert errors == [], f"execute_job raised instead of standing down: {errors}"
    assert outcomes == [StopReason.OWNERSHIP_LOST]

    assert handler.units_executed == 0, (
        "H-6: the stale worker executed the unit effect after ownership transferred "
        f"(owner seen at effect start: {handler.owner_at_effect_start})"
    )
    assert handler.owner_at_effect_start == []
    assert _snapshot(db_settings, job_id) == baseline, (
        "the stale worker mutated the new owner's job"
    )


# ---------------------------------------------------------------------------
# The expired-but-unreaped design decision, made explicit
# ---------------------------------------------------------------------------


def test_expired_but_unreaped_lease_is_still_renewable_by_its_owner(
    clean_jobs, db_settings
) -> None:
    """Required coverage 6. This is a deliberate design choice, pinned here.

    ``renew_lease`` carries no expiry predicate: in this design *reaping*
    transfers ownership, not the clock. A worker that is still the durable
    owner may therefore renew a lapsed lease, which is what lets the
    heartbeat keep a genuinely-running unit alive across a momentary lapse.

    Beginning a *new* effect on a lapsed lease is refused instead -- see
    ``test_expired_lease_owner_may_not_begin_an_effect``. Keeping a running
    unit alive and starting a new one are different questions and get
    different answers. Changing either half should break one of these two
    tests, deliberately.
    """
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)
    _expire(db_settings, job_id)

    with session_scope(db_settings) as s:
        assert renew_lease(s, job_id, 300, worker_id=worker_a) is True, (
            "the still-durable owner could not renew its own lapsed lease"
        )

    with session_scope(db_settings) as s:
        assert reap_expired_leases(s) == [], "the reaper reclaimed a freshly renewed lease"
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.lease_owner == worker_a
        assert row.status is JobStatus.RUNNING


def test_a_reaped_lease_is_not_renewable_by_its_previous_owner(clean_jobs, db_settings) -> None:
    """The other half of the same decision: once the reaper has acted, no."""
    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)

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
        assert job_id in reap_expired_leases(s)

    with session_scope(db_settings) as s:
        assert renew_lease(s, job_id, 300, worker_id=worker_a) is False, (
            "a reaped job was renewed by its previous owner"
        )


# ---------------------------------------------------------------------------
# H-7 — BLOCKED through the real worker loop
# ---------------------------------------------------------------------------


class _GatedBlockedHandler:
    """Raises a genuine blocked_reason error after a gate."""

    def __init__(self) -> None:
        # The handler registry is process-global and refuses duplicates, so
        # each instance claims its own type rather than fighting over one.
        self.job_type = f"test.blocked_gate.{uuid.uuid4().hex[:8]}"
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
            technical_detail="acceptance H-7",
            remediation="Install a provider that serves it.",
            blocked_reason=BlockedReason.MISSING_PROVIDER.value,
        )


def _build_worker(db_settings: Settings):
    from continuum_worker.main import Worker

    worker = Worker(db_settings)
    worker.register()
    return worker


def _run_once(worker: Any) -> tuple[list[BaseException], threading.Event]:
    errors: list[BaseException] = []
    finished = threading.Event()

    def run() -> None:
        try:
            worker.run_once()
        # Deliberately BaseException: an escape kills the worker loop.
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True).start()
    return errors, finished


def test_blocked_after_ownership_loss_stands_down_without_crashing(clean_jobs, db_settings) -> None:
    """Required coverage 7, through the real ``Worker.run_once()``."""
    handler = _GatedBlockedHandler()
    registry.register(handler)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    with session_scope(db_settings) as s:
        worker_b = register_worker(s).id

    errors, finished = _run_once(worker_a)
    assert handler.entered.wait(30), "the unit never started"

    with session_scope(db_settings) as s:
        job_id = s.execute(select(Job.id).where(Job.job_type == handler.job_type)).scalar_one()
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    handler.release.set()
    assert finished.wait(60), "run_once never returned"

    after = _snapshot(db_settings, job_id)
    assert after == baseline, (
        f"a stale worker wrote BLOCKED onto the new owner's job.\nbefore={baseline}\nafter={after}"
    )
    assert after["status"] is not JobStatus.BLOCKED
    assert after["blocked_reason"] is None
    assert errors == [], (
        f"{type(errors[0]).__name__ if errors else ''} escaped Worker.run_once() "
        f"and would terminate run_forever(): {errors}"
    )


def test_blocked_while_still_owner_lands_blocked_normally(clean_jobs, db_settings) -> None:
    """Required coverage 8. The stand-down must not cost the ordinary path."""
    handler = _GatedBlockedHandler()
    handler.release.set()
    registry.register(handler)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    errors, finished = _run_once(worker_a)
    assert finished.wait(60)
    assert errors == [], f"run_once raised: {errors}"

    with session_scope(db_settings) as s:
        job = s.execute(select(Job).where(Job.job_type == handler.job_type)).scalar_one()
        assert job.status is JobStatus.BLOCKED
        assert job.blocked_reason is BlockedReason.MISSING_PROVIDER
        assert job.remediation, "the BLOCKED payload must stay actionable"
        assert job.last_error is None, "a block is a decision, not a failure"


# ---------------------------------------------------------------------------
# H-7b — the unknown-handler BLOCKED path
# ---------------------------------------------------------------------------


def test_unknown_handler_after_ownership_loss_does_not_crash_the_worker(
    clean_jobs, db_settings, monkeypatch
) -> None:
    """Required coverage 9. This path never enters ``execute_job``."""
    import importlib

    # ``continuum_worker/__init__`` binds the *function* ``main``, shadowing
    # the submodule for attribute access; importlib returns the real module.
    worker_main = importlib.import_module("continuum_worker.main")

    unknown_type = f"test.unknown.{uuid.uuid4().hex[:8]}"
    with session_scope(db_settings) as s:
        enqueue(s, unknown_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    with session_scope(db_settings) as s:
        worker_b = register_worker(s).id

    at_block, release_block = threading.Event(), threading.Event()
    real_block = worker_main.Worker._block_or_stand_down

    def gated(self, *args: Any, **kwargs: Any):
        at_block.set()
        assert release_block.wait(60)
        return real_block(self, *args, **kwargs)

    monkeypatch.setattr(worker_main.Worker, "_block_or_stand_down", gated)

    errors, finished = _run_once(worker_a)
    assert at_block.wait(30), "the BLOCKED mutation was never reached"

    with session_scope(db_settings) as s:
        job_id = s.execute(select(Job.id).where(Job.job_type == unknown_type)).scalar_one()
    _steal(db_settings, job_id, worker_b)
    baseline = _snapshot(db_settings, job_id)
    assert baseline["owner"] == worker_b

    release_block.set()
    assert finished.wait(60), "run_once never returned"

    after = _snapshot(db_settings, job_id)
    assert after == baseline, "a stale worker overwrote the new owner's job with BLOCKED"
    assert errors == [], (
        f"{type(errors[0]).__name__ if errors else ''} escaped Worker.run_once() "
        f"and would terminate run_forever(): {errors}"
    )


def test_unknown_handler_while_still_owner_lands_blocked_normally(clean_jobs, db_settings) -> None:
    """Required coverage 10."""
    unknown_type = f"test.unknown.{uuid.uuid4().hex[:8]}"
    with session_scope(db_settings) as s:
        enqueue(s, unknown_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    errors, finished = _run_once(worker_a)
    assert finished.wait(60)
    assert errors == [], f"run_once raised: {errors}"

    with session_scope(db_settings) as s:
        job = s.execute(select(Job).where(Job.job_type == unknown_type)).scalar_one()
        assert job.status is JobStatus.BLOCKED
        assert job.blocked_reason is BlockedReason.MISSING_PROVIDER
        assert job.remediation, "the BLOCKED payload must stay actionable"
        assert job.last_error is None


def test_worker_loop_survives_an_ownership_loss_stand_down(clean_jobs, db_settings) -> None:
    """Required coverage 11. The worker keeps working afterwards.

    A stand-down that leaves the process alive but wedged would satisfy every
    other assertion here and still be useless.
    """
    handler = _GatedBlockedHandler()
    registry.register(handler)

    with session_scope(db_settings) as s:
        enqueue(s, handler.job_type, payload={"case": str(uuid.uuid4())})

    worker_a = _build_worker(db_settings)
    with session_scope(db_settings) as s:
        worker_b = register_worker(s).id

    errors, finished = _run_once(worker_a)
    assert handler.entered.wait(30)

    with session_scope(db_settings) as s:
        job_id = s.execute(select(Job.id).where(Job.job_type == handler.job_type)).scalar_one()
    _steal(db_settings, job_id, worker_b)

    handler.release.set()
    assert finished.wait(60)
    assert errors == []

    # The same worker now picks up and completes an ordinary job.
    normal = _Handler(units=2, settings=db_settings)
    normal.job_type = f"test.effect_start.{uuid.uuid4().hex[:8]}"
    registry.register(normal)
    with session_scope(db_settings) as s:
        # Release B's hold so the next claim is unambiguous.
        s.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.CANCELLED, lease_owner=None, lease_expires_at=None)
        )
        enqueue(s, normal.job_type, payload={"case": str(uuid.uuid4())})

    assert worker_a.run_once() is True, "the worker did no further work after standing down"

    with session_scope(db_settings) as s:
        job = s.execute(select(Job).where(Job.job_type == normal.job_type)).scalar_one()
        assert job.status is JobStatus.SUCCEEDED
        assert job.units_done == 2


# ---------------------------------------------------------------------------
# F-A — the handover helper must be deterministic
# ---------------------------------------------------------------------------


def test_a_beat_cannot_renew_a_lease_inside_the_expire_and_reap_transaction(
    clean_jobs, db_settings
) -> None:
    """Required coverage 12, the mechanism, proved deterministically.

    F-A was not "the helper is sometimes slow". It was a specific race: with
    the expiry in one transaction and the reap in another, a heartbeat beat
    landing between them renewed the very lease being expired -- legitimately,
    since ``renew_lease`` carries no expiry predicate -- after which the
    reaper found nothing and the handover silently failed.

    Sharing one transaction closes it, and this proves *why* rather than
    observing that failures stopped: a concurrent renewal is forced into the
    gap, observed **blocked on the row lock**, and then refused once the
    reap commits.
    """
    from continuum_jobs import renew_lease

    job_id, worker_a, _worker_b = _prepare(clean_jobs, lease_seconds=30)

    renewed: list[bool] = []
    attempted = threading.Event()
    beat_done = threading.Event()

    def beat() -> None:
        try:
            with session_scope(db_settings) as s:
                attempted.set()
                renewed.append(renew_lease(s, job_id, 300, worker_id=worker_a))
        finally:
            beat_done.set()

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
        # The row lock is now held by this transaction. Force a beat into the
        # gap the old helper left open.
        threading.Thread(target=beat, daemon=True).start()
        assert attempted.wait(30)
        assert _await_contention(db_settings, beat_done) == "blocked", (
            "the concurrent renewal was not blocked by the expire/reap transaction"
        )
        assert job_id in reap_expired_leases(s), "the reaper did not reclaim the job"

    assert beat_done.wait(30), "the blocked renewal never completed"
    assert renewed == [False], f"a beat renewed a lease the reaper had just reclaimed: {renewed}"

    with session_scope(db_settings) as s:
        row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
        assert row.status is JobStatus.QUEUED
        assert row.lease_owner is None


def test_ownership_handover_helper_is_deterministic_under_a_live_heartbeat(
    clean_jobs, db_settings
) -> None:
    """Required coverage 12.

    The old helper expired the lease in one transaction and reaped in
    another. A heartbeat beat landing in that gap renewed the very lease
    being expired -- ``renew_lease`` has no expiry predicate -- after which
    the reaper found nothing and the handover silently failed, at roughly one
    run in ten.

    Here the handover is exercised repeatedly against a heartbeat beating as
    fast as it is allowed to. Every iteration must succeed; a single failure
    is the flake.
    """
    from continuum_jobs import LeaseHeartbeat

    for iteration in range(12):
        job_id, worker_a, worker_b = _prepare(clean_jobs, lease_seconds=30)
        with LeaseHeartbeat(
            db_settings,
            job_id=job_id,
            worker_id=worker_a,
            lease_seconds=30,
            interval_seconds=0.01,
        ):
            _steal(db_settings, job_id, worker_b)

        with session_scope(db_settings) as s:
            row = s.execute(select(Job).where(Job.id == job_id)).scalar_one()
            assert row.lease_owner == worker_b, (
                f"handover {iteration} did not take effect under a live heartbeat"
            )
            s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=JobStatus.CANCELLED, lease_owner=None, lease_expires_at=None)
            )


def test_rightful_owner_completes_normally(clean_jobs, db_settings) -> None:
    """Required coverage 5. The three H-6 layers cost the ordinary path nothing."""
    job_id, worker_a, _worker_b = _prepare(clean_jobs)
    handler = _Handler(units=3, settings=db_settings)

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
    assert handler.units_executed == 3
    assert handler.owner_at_effect_start == [worker_a, worker_a, worker_a]
    assert handler.lease_alive_at_effect_start == [True, True, True]

    after = _snapshot(db_settings, job_id)
    assert after["status"] is JobStatus.SUCCEEDED
    assert after["units_done"] == 3
    assert all(s[1] is StepStatus.SUCCEEDED for s in after["steps"])  # type: ignore[union-attr]
    assert all(s[2] == 1 for s in after["steps"]), "a unit was started more than once"  # type: ignore[union-attr]
