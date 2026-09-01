"""Worker routes: list and drain.

``POST /workers/{id}/drain`` is the portable half of graceful shutdown
(F-31). Windows has no real ``SIGTERM``, and a taskkill is unconditional, so
a signal-only design would be untested on the platform this project actually
runs on. The flag is polled by the worker between units, works identically
everywhere, survives the API being down afterwards, and makes graceful stop
a testable state transition rather than a signal-delivery race.

This is **not** an API-to-worker control channel: the API writes a row and
the worker reads it. All coordination remains PostgreSQL (A-02).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from continuum_db.models import Worker
from continuum_db.session import session_scope
from continuum_jobs import reap_expired_leases, request_drain
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select

from continuum_api.schemas import WorkerOut

router = APIRouter(prefix="/workers", tags=["workers"])


def _settings(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.settings


@router.get("", response_model=list[WorkerOut])
def list_workers(
    request: Request,
    include_stopped: Annotated[bool, Query()] = False,
) -> list[WorkerOut]:
    """Live worker inventory, so the queue view can be honest about capacity."""
    with session_scope(_settings(request)) as session:
        query = select(Worker).order_by(Worker.started_at.desc())
        if not include_stopped:
            query = query.where(Worker.stopped_at.is_(None))
        return [WorkerOut.model_validate(row) for row in session.execute(query).scalars()]


@router.post("/{worker_id}/drain", response_model=WorkerOut)
def drain(request: Request, worker_id: uuid.UUID) -> WorkerOut:
    """Ask a worker to finish its current unit and stop.

    The job it is running is left resumable from its completed units; it is
    not cancelled. Acceptance test 110.9.
    """
    with session_scope(_settings(request)) as session:
        worker = session.get(Worker, worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="worker not found")
        if worker.stopped_at is not None:
            raise HTTPException(status_code=409, detail="worker has already stopped")
        request_drain(session, worker_id)
        session.flush()
        session.refresh(worker)
        return WorkerOut.model_validate(worker)


@router.post("/reap", response_model=dict)
def reap(request: Request) -> dict[str, object]:
    """Return jobs whose worker died to the queue (F-27).

    Normally the worker loop does this on its own schedule. Exposed so an
    operator can force recovery immediately after a crash rather than waiting
    out the lease, and so acceptance test 110.11 can trigger it deterministically.
    """
    with session_scope(_settings(request)) as session:
        recovered = reap_expired_leases(session)
        return {"recovered": [str(job_id) for job_id in recovered], "count": len(recovered)}
