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

from continuum_jobs.queue import record_event, transition

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


def renew_lease(session: Session, job_id: uuid.UUID, lease_seconds: int) -> None:
    """Extend the lease on a job still being worked."""
    session.execute(
        update(Job)
        .where(Job.id == job_id)
        .values(lease_expires_at=func.now() + func.make_interval(0, 0, 0, 0, 0, 0, lease_seconds))
    )
    record_event(session, job_id, JobEventType.LEASE_RENEWED)


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
        self._thread: threading.Thread | None = None
        self.beats = 0
        self.errors = 0

    def _run(self) -> None:
        from continuum_db.session import session_scope

        while not self._stop.wait(self._interval):
            try:
                with session_scope(self._settings) as session:
                    renew_lease(session, self._job_id, self._lease_seconds)
                    heartbeat(session, self._worker_id)
                self.beats += 1
            except Exception:
                self.errors += 1
                log.warning(
                    "lease heartbeat failed",
                    extra={"job_id": str(self._job_id), "worker_id": str(self._worker_id)},
                )

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
    stale = (
        session.execute(
            select(Job).where(
                Job.status == JobStatus.RUNNING,
                Job.lease_expires_at.is_not(None),
                Job.lease_expires_at < cutoff,
            )
        )
        .scalars()
        .all()
    )

    recovered: list[uuid.UUID] = []
    for job in stale:
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
