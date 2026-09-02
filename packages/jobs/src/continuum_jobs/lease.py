"""Worker registration, heartbeats and expired-lease recovery (F-27, F-31).

Two problems solved here:

* **A hard-killed worker must not strand its job.** Without a lease, a job
  left in ``RUNNING`` is indistinguishable from one genuinely running, and it
  sits there forever. The reaper returns expired-lease jobs to the queue;
  combined with effect idempotency (execution.py) the retry is safe.
* **Graceful stop must work on Windows.** Windows has no real ``SIGTERM``, so
  a signal-only design would be untested on the platform this project
  actually runs on. ``worker.drain_requested`` is a database-visible flag
  polled between units: it works identically everywhere, survives the API
  being down, and makes graceful stop a testable state transition.

Every timestamp here comes from the DATABASE clock (D-09).
"""

from __future__ import annotations

import os
import platform
import threading
import uuid
from typing import Any, cast

from continuum_config import Settings
from continuum_core import uuid7
from continuum_db.enums import JobEventType, JobStatus
from continuum_db.models import Job, Worker
from continuum_observability import get_logger
from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from continuum_jobs.queue import _database_now, record_event, transition

__all__ = [
    "LeaseHeartbeat",
    "hardware_signature",
    "heartbeat",
    "reap_expired_leases",
    "register_worker",
    "renew_lease",
    "request_drain",
    "stop_worker",
    "worker_should_drain",
]

log = get_logger("continuum.jobs.lease")


def hardware_signature() -> str:
    """A coarse machine fingerprint for throughput telemetry (F-60).

    A plain string, deliberately not a ``HardwareExecutionProfile`` entity:
    that would be solving hardware-aware scheduling before a single real job
    has ever run. Samples can be partitioned by this later with no migration.
    """
    return f"{platform.system()}-{platform.machine()}-cpu{os.cpu_count() or 0}"


def register_worker(session: Session, *, resource_classes: str = "cpu") -> Worker:
    """Announce this process as a live worker."""
    worker = Worker(
        id=uuid7(),
        hostname=platform.node()[:255],
        pid=os.getpid(),
        resource_classes=resource_classes,
        hardware_signature=hardware_signature(),
    )
    session.add(worker)
    session.flush()
    log.info(
        "worker registered",
        extra={"worker_id": str(worker.id), "pid": worker.pid, "classes": resource_classes},
    )
    return worker


def heartbeat(session: Session, worker_id: uuid.UUID) -> None:
    """Refresh liveness. Cheap, called between units."""
    session.execute(
        update(Worker).where(Worker.id == worker_id).values(last_heartbeat_at=func.now())
    )


def renew_lease(
    session: Session,
    job_id: uuid.UUID,
    lease_seconds: int,
    *,
    worker_id: uuid.UUID | None = None,
) -> bool:
    """Extend the lease on a job, **only if this worker still owns it**.

    Returns ``True`` when the lease was extended and ``False`` when it was
    not — because the job is no longer ``RUNNING``, or is owned by a
    different worker, or no longer exists.

    Renewing by job id alone (the previous behaviour) let a worker that had
    already lost the job push the lease forward anyway, papering over the
    very condition the lease exists to detect. Ownership is therefore part of
    the ``WHERE`` clause rather than something the caller is trusted to have
    checked: the guard and the write are then a single atomic statement.
    """
    conditions = [Job.id == job_id, Job.status == JobStatus.RUNNING]
    if worker_id is not None:
        conditions.append(Job.lease_owner == worker_id)

    result = session.execute(
        update(Job)
        .where(*conditions)
        .values(lease_expires_at=func.now() + func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds))
    )
    renewed = bool(cast("CursorResult[Any]", result).rowcount)

    if renewed:
        record_event(session, job_id, JobEventType.LEASE_RENEWED)
    return renewed


class LeaseHeartbeat:
    """Renew a job's lease on a background thread while a unit executes.

    **The defect this closes:** renewing only *between* units means a unit
    that runs longer than ``worker_lease_seconds`` has its lease expire while
    it is still working. The reaper then reclaims live work, a second worker
    claims the same job, and both execute the same unit concurrently. Effect
    idempotency keeps the stored artifact correct, but the duplicated compute
    is real and, for a multi-hour render, expensive.

    ``worker_heartbeat_seconds`` was configured and never used; this is what
    uses it.

    The thread opens its **own** session per beat: a SQLAlchemy Session is not
    thread-safe, so sharing the executing session would be a data race far
    worse than the problem being fixed.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        job_id: uuid.UUID,
        worker_id: uuid.UUID,
        lease_seconds: int,
        interval_seconds: float,
    ) -> None:
        self._settings = settings
        self._job_id = job_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        # Never beat slower than a third of the lease: two consecutive misses
        # must still leave time to renew before expiry.
        self._interval = max(0.1, min(interval_seconds, lease_seconds / 3))
        self._stop = threading.Event()
        self._ownership_lost = threading.Event()
        self._thread: threading.Thread | None = None
        # Give up once failures have spanned roughly a whole lease: by then
        # the lease has expired from every other worker's point of view.
        self._max_consecutive_errors = max(2, int(lease_seconds / self._interval) + 1)
        self.beats = 0
        self.errors = 0
        self.consecutive_errors = 0

    @property
    def ownership_lost(self) -> bool:
        """True once this worker is known to no longer own the job.

        Set either because a renewal was refused (the job is no longer
        RUNNING, or is owned by someone else) or because renewal has failed
        often enough that continuing to assume ownership is not defensible.
        """
        return self._ownership_lost.is_set()

    def _run(self) -> None:
        from continuum_db.session import session_scope

        while not self._stop.wait(self._interval):
            try:
                with session_scope(self._settings) as session:
                    renewed = renew_lease(
                        session,
                        self._job_id,
                        self._lease_seconds,
                        worker_id=self._worker_id,
                    )
                    heartbeat(session, self._worker_id)
            except Exception:
                self.errors += 1
                self.consecutive_errors += 1
                log.warning(
                    "lease heartbeat failed",
                    extra={
                        "job_id": str(self._job_id),
                        "worker_id": str(self._worker_id),
                        "consecutive_errors": self.consecutive_errors,
                    },
                )
                # A transient blip is fine; silence for longer than the lease
                # is not. Past that point the lease has provably expired as
                # far as any other worker can tell, so continuing to behave
                # as the owner is exactly the fiction this class exists to
                # prevent (second audit C-1).
                if self.consecutive_errors >= self._max_consecutive_errors:
                    log.error(
                        "lease heartbeat failed past the lease window; relinquishing ownership",
                        extra={
                            "job_id": str(self._job_id),
                            "worker_id": str(self._worker_id),
                            "consecutive_errors": self.consecutive_errors,
                        },
                    )
                    self._ownership_lost.set()
                    return
                continue

            self.consecutive_errors = 0

            if not renewed:
                # Refused, not failed: another worker owns this job now, or it
                # is no longer RUNNING. Stop beating and say so, rather than
                # looping forever pretending nothing changed.
                log.warning(
                    "lease renewal refused; this worker no longer owns the job",
                    extra={"job_id": str(self._job_id), "worker_id": str(self._worker_id)},
                )
                self._ownership_lost.set()
                return

            self.beats += 1

    def __enter__(self) -> LeaseHeartbeat:
        self._thread = threading.Thread(
            target=self._run,
            name=f"continuum-lease-{self._job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            # Bounded join: a stuck beat must not hold the worker hostage.
            self._thread.join(timeout=self._interval + 5.0)


def worker_should_drain(session: Session, worker_id: uuid.UUID) -> bool:
    """Whether a graceful stop has been requested for this worker.

    The portable half of graceful shutdown: polled between units, works on
    Windows where signals do not, and stays observable in the UI.
    """
    value = session.execute(
        select(Worker.drain_requested).where(Worker.id == worker_id)
    ).scalar_one_or_none()
    return bool(value)


def request_drain(session: Session, worker_id: uuid.UUID) -> bool:
    """Ask a worker to finish its current unit and stop."""
    result = session.execute(
        update(Worker)
        .where(Worker.id == worker_id, Worker.stopped_at.is_(None))
        .values(drain_requested=True)
    )
    return bool(cast("CursorResult[Any]", result).rowcount)


def stop_worker(session: Session, worker_id: uuid.UUID) -> None:
    """Mark the worker stopped on clean exit."""
    session.execute(update(Worker).where(Worker.id == worker_id).values(stopped_at=func.now()))


def reap_expired_leases(session: Session, *, grace_seconds: int = 0) -> list[uuid.UUID]:
    """Return jobs whose worker died to the queue.

    This is what makes crash recovery automatic instead of manual. Safety
    depends on effect idempotency: a reclaimed job re-runs only its
    incomplete units, and re-running a completed unit is a byte-identical
    no-op (ADR-0002 section 2).
    """
    cutoff = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, grace_seconds)

    # `FOR UPDATE` is the whole fix (second audit C-1).
    #
    # The previous version SELECTed without a lock, decided from that snapshot,
    # and wrote QUEUED later. A live worker could commit a fresh heartbeat in
    # between, and the reaper would then overwrite it -- moving genuinely
    # RUNNING work back to QUEUED so a second worker could claim it. Content
    # addressing keeps the artifact correct but does nothing about duplicate
    # compute, and nothing at all about a non-content effect.
    #
    # Locking makes the decision and the write one serialized unit per row.
    # It also engages PostgreSQL's EvalPlanQual: when this SELECT blocks on a
    # row another transaction is updating, it re-evaluates the WHERE clause
    # against the *new* row version once that transaction commits. A row whose
    # lease was just pushed into the future therefore fails
    # `lease_expires_at < cutoff` and is never returned at all.
    #
    # SKIP LOCKED keeps several reapers from serialising behind each other:
    # a row another reaper is already handling is not this reaper's business.
    stale = (
        session.execute(
            select(Job)
            .where(
                Job.status == JobStatus.RUNNING,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        .scalars()
        .all()
    )

    recovered: list[uuid.UUID] = []
    for job in stale:
        # Explicit re-verification under the lock, belt-and-braces alongside
        # EvalPlanQual. Stated outright rather than relied upon implicitly:
        # if someone later drops the predicate from the locking SELECT, this
        # still refuses to reap a job whose lease is now live, and the reason
        # is visible at the point of decision instead of buried in PostgreSQL
        # visibility semantics.
        session.refresh(job)
        if job.status is not JobStatus.RUNNING:
            continue
        if job.lease_expires_at is None or job.lease_expires_at >= _database_now(session):
            log.info(
                "skipped reaping a job whose lease was renewed after observation",
                extra={"job_id": str(job.id), "lease_owner": str(job.lease_owner)},
            )
            continue

        previous_owner = job.lease_owner
        record_event(
            session,
            job.id,
            JobEventType.LEASE_EXPIRED,
            worker_id=previous_owner,
            detail={
                "expired_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
                "attempt": job.attempt,
            },
        )
        job.lease_owner = None
        job.lease_expires_at = None
        job.attempt += 1

        if job.attempt >= job.max_attempts:
            transition(
                session,
                job,
                JobStatus.FAILED_FINAL,
                detail={"reason": "lease expired and attempts exhausted"},
            )
        else:
            job.run_after = session.execute(select(func.now())).scalar_one()
            transition(session, job, JobStatus.QUEUED, detail={"reason": "lease expired"})
            recovered.append(job.id)

        log.warning(
            "reclaimed job from expired lease",
            extra={"job_id": str(job.id), "previous_owner": str(previous_owner)},
        )

    session.flush()
    return recovered
