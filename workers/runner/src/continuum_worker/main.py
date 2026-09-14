"""The standalone worker process (ADR-0002 sections 12-13).

**This is a service, never a child of the UI or the API.** A ``uvicorn
--reload`` restart or a Next.js hot reload must not be able to kill it, and
a future desktop wrapper must attach to an already-running worker rather
than spawning one as a child of its window -- Electron and Tauri kill child
processes on window close by default, which is exactly the trap Master Plan
section 91.4 warns about.

Because of that separation, acceptance 110.8 ("closing the web UI does not
cancel the worker job") is *structurally* true rather than incidentally so:
there is no channel between them to carry a cancellation.

Shutdown is graceful through two channels that share one code path:

1. ``SIGINT``/``SIGTERM`` where the platform provides them;
2. ``worker.drain_requested`` in the database, polled between units.

Windows has no real ``SIGTERM``, so the flag is not a convenience -- it is
the only channel that works on the platform this project actually runs on.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
import types
import uuid

from continuum_config import Settings, get_settings
from continuum_core import BlockedReason, ContinuumError
from continuum_db.models import Job
from continuum_db.session import session_scope
from continuum_jobs import (
    JobOwnershipLostError,
    StaleJobStateError,
    UnknownJobTypeError,
    apply_pending_requests,
    block_job,
    claim_next_job,
    execute_job,
    heartbeat,
    reap_expired_leases,
    record_ownership_loss,
    register_worker,
    registry,
    stop_worker,
    unblock_ready_dependents,
    worker_should_drain,
)
from continuum_observability import configure_logging, correlation_scope, get_logger
from continuum_providers import build_default_registry
from continuum_storage import build_storage
from sqlalchemy.orm import Session

from continuum_worker.handlers.catalog import (
    CatalogHashHandler,
    CatalogScanHandler,
    CollectionImportHandler,
    MemberExtractHandler,
)
from continuum_worker.handlers.rough import RoughAttemptHandler
from continuum_worker.handlers.synthetic import (
    BlockedCapabilityHandler,
    CountedWorkHandler,
)

__all__ = ["Worker", "main", "register_default_handlers"]

log = get_logger("continuum.worker")

_shutdown_requested = False


def _handle_signal(signum: int, _frame: types.FrameType | None) -> None:
    """Ask the loop to stop after the current unit. Never kills mid-unit."""
    global _shutdown_requested
    _shutdown_requested = True
    log.info("shutdown signal received", extra={"signal": signum})


def register_default_handlers() -> None:
    """The synthetic Phase 0 handlers, the Phase 1 rough attempt renderer and the
    Phase 1.5 catalog jobs."""
    known = set(registry.known_types())
    for handler in (
        CountedWorkHandler(),
        BlockedCapabilityHandler(),
        RoughAttemptHandler(),
        CatalogScanHandler(),
        CatalogHashHandler(),
        CollectionImportHandler(),
        MemberExtractHandler(),
    ):
        if handler.job_type not in known:
            registry.register(handler)


class Worker:
    """Claim -> execute -> repeat, with leases, heartbeats and reaping."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.resource_classes = [
            c.strip() for c in self.settings.worker_resource_classes.split(",") if c.strip()
        ]
        self.concurrency_limits = {
            "cpu": self.settings.max_concurrency_cpu,
            "gpu": self.settings.max_concurrency_gpu,
        }
        self.storage = build_storage(self.settings, create=True)
        self.providers = build_default_registry()
        self.worker_id: uuid.UUID | None = None
        self._last_reap = 0.0

    def register(self) -> uuid.UUID:
        with session_scope(self.settings) as session:
            worker = register_worker(session, resource_classes=",".join(self.resource_classes))
            self.worker_id = worker.id
        return self.worker_id

    def should_stop(self) -> bool:
        """True when a signal arrived or a drain was requested in the database."""
        if _shutdown_requested:
            return True
        if self.worker_id is None:
            return False
        with session_scope(self.settings) as session:
            return worker_should_drain(session, self.worker_id)

    def run_once(self) -> bool:
        """Claim and run at most one job. Returns True if work was done."""
        assert self.worker_id is not None

        self._maybe_reap()

        with session_scope(self.settings) as session:
            heartbeat(session, self.worker_id)
            # Worker-owned: the API only ever sets flags (ADR-0002 section 4).
            apply_pending_requests(session)
            job = claim_next_job(
                session,
                worker_id=self.worker_id,
                resource_classes=self.resource_classes,
                lease_seconds=self.settings.worker_lease_seconds,
                concurrency_limits=self.concurrency_limits,
            )
            job_id = job.id if job else None

        if job_id is None:
            return False

        with session_scope(self.settings) as session:
            job = session.get(Job, job_id)
            if job is None:  # pragma: no cover - deleted mid-flight
                return False

            with correlation_scope(job.correlation_id):
                try:
                    handler = registry.get(job.job_type)
                except UnknownJobTypeError as exc:
                    # A job type with no handler is a configuration problem,
                    # not a failure: the job waits until the handler exists.
                    self._park(
                        session,
                        job_id,
                        BlockedReason.MISSING_PROVIDER,
                        {
                            "message": exc.user_message,
                            "action": exc.remediation or "Register the handler.",
                        },
                    )
                    return True

                try:
                    reason = execute_job(
                        session,
                        job,
                        handler,
                        worker_id=self.worker_id,
                        lease_seconds=self.settings.worker_lease_seconds,
                        derived=self.storage.derived,
                        providers=self.providers,
                        settings=self.settings,
                        heartbeat_seconds=self.settings.worker_heartbeat_seconds,
                    )
                    log.info(
                        "job finished",
                        extra={"job_id": str(job.id), "outcome": reason.value},
                    )
                except ContinuumError as exc:
                    # A capability nothing can serve, or a source that is not
                    # reachable, is a BLOCKED state with remediation, not a
                    # failure: the recipe survives and the user is told what is
                    # missing (F-24, F-34). execute_job re-raises only errors
                    # that carry a blocked_reason; anything else is a bug here.
                    if not exc.context.get("blocked_reason"):
                        raise
                    session.rollback()
                    self._park(
                        session,
                        job_id,
                        _blocked_reason_from(exc),
                        {
                            "message": exc.user_message,
                            "action": exc.remediation or "",
                            **exc.context,
                        },
                    )
        # A job that just finished may be the last prerequisite of another:
        # release it now rather than at the next recovery pass.
        with session_scope(self.settings) as session:
            unblock_ready_dependents(session)
        return True

    def _park(
        self,
        session: Session,
        job_id: uuid.UUID,
        reason: BlockedReason,
        remediation: dict[str, object],
    ) -> None:
        """Move this worker's running job to BLOCKED - only while it owns it.

        Ownership is proven under the row lock by ``block_job(owner=...)``.
        If the job was reaped or claimed elsewhere in the meantime, this
        worker writes nothing but its own stand-down event (final audit H-3).
        """
        assert self.worker_id is not None
        job = session.get(Job, job_id)
        if job is None:  # pragma: no cover - deleted mid-flight
            return
        try:
            block_job(
                session,
                job,
                reason,
                remediation,
                worker_id=self.worker_id,
                owner=self.worker_id,
            )
        except (JobOwnershipLostError, StaleJobStateError):
            session.rollback()
            record_ownership_loss(session, job_id, self.worker_id)

    def _maybe_reap(self) -> None:
        """Recover jobs whose worker died (F-27). Cheap, so run it regularly."""
        now = time.monotonic()
        if now - self._last_reap < self.settings.worker_lease_seconds:
            return
        self._last_reap = now
        with session_scope(self.settings) as session:
            recovered = reap_expired_leases(session)
            released = unblock_ready_dependents(session)
        if recovered or released:
            log.info(
                "recovery pass",
                extra={"reclaimed": len(recovered), "unblocked": released},
            )

    def run_forever(self) -> int:
        worker_id = self.register()
        log.info(
            "worker started",
            extra={
                "worker_id": str(worker_id),
                "resource_classes": self.resource_classes,
                "vault_protection": self.storage.vault_protection.status.value,
            },
        )
        try:
            while not self.should_stop():
                did_work = self.run_once()
                if not did_work:
                    time.sleep(self.settings.worker_poll_seconds)
        finally:
            with session_scope(self.settings) as session:
                stop_worker(session, worker_id)
            log.info("worker stopped cleanly", extra={"worker_id": str(worker_id)})
        return 0


def _blocked_reason_from(exc: ContinuumError) -> BlockedReason:
    """Map the provider policy's reason onto the durable enum."""
    raw = exc.context.get("blocked_reason")
    if not isinstance(raw, str):
        return BlockedReason.MISSING_PROVIDER
    try:
        return BlockedReason(raw)
    except ValueError:
        return BlockedReason.MISSING_PROVIDER


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="continuum-worker",
        description="Continuum durable worker. A service, never a child of the UI.",
    )
    parser.add_argument("--once", action="store_true", help="Run one job then exit.")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    register_default_handlers()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):  # pragma: no cover - platform dependent
            pass

    worker = Worker(settings)
    if args.once:
        worker.register()
        worker.run_once()
        return 0
    return worker.run_forever()


if __name__ == "__main__":
    sys.exit(main())
