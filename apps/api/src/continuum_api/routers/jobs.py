"""Job routes: list, get, enqueue, pause, resume, cancel, retry.

The API is a **client** of the job system, not its owner (Master Plan
section 91). It writes request flags and reads state; it never executes work
and never writes ``status`` directly -- only the worker and the lease reaper
do that, through the guarded transition table (F-28).

No route accepts a filesystem path (F-50).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from continuum_core import BlockedReason, ContinuumError, JobStatus
from continuum_db.models import Job, JobEvent
from continuum_db.session import session_scope
from continuum_jobs import (
    enqueue as enqueue_job,
)
from continuum_jobs import (
    request_cancel,
    request_pause,
    resume_job,
    retry_job,
)
from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from continuum_api.schemas import EnqueueJobRequest, JobDetail, JobEventOut, JobStepOut, JobSummary

EtaState = Literal["estimating", "estimated", "unknown"]

router = APIRouter(prefix="/jobs", tags=["jobs"])

#: How many recent audit events a detail view returns.
_EVENT_WINDOW = 50


def _settings(request: Request):  # type: ignore[no-untyped-def]
    return request.app.state.settings


@router.get("", response_model=list[JobSummary])
def list_jobs(
    request: Request,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    job_type: Annotated[str | None, Query(max_length=128)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[JobSummary]:
    with session_scope(_settings(request)) as session:
        query = select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
        if job_status is not None:
            query = query.where(Job.status == job_status)
        if job_type is not None:
            query = query.where(Job.job_type == job_type)
        rows = session.execute(query).scalars().all()
        return [JobSummary.model_validate(row) for row in rows]


@router.get("/{job_id}", response_model=JobDetail)
def get_job(request: Request, job_id: uuid.UUID) -> JobDetail:
    with session_scope(_settings(request)) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")

        events = (
            session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id)
                .order_by(JobEvent.created_at.desc())
                .limit(_EVENT_WINDOW)
            )
            .scalars()
            .all()
        )

        detail = JobDetail.model_validate(job)
        detail.steps = [JobStepOut.model_validate(s) for s in job.steps]
        detail.recent_events = [JobEventOut.model_validate(e) for e in events]
        detail.eta_seconds, detail.eta_state = _estimate_eta(job)
        return detail


def _estimate_eta(job: Job) -> tuple[float | None, EtaState]:
    """Conservative ETA (Master Plan section 91.6).

    Returns ``estimating`` until enough units have completed to say anything
    honest. A confident wrong number is worse than admitting we do not know
    yet, especially for a multi-hour local render.
    """
    minimum_samples = 3
    if not job.units_total or job.units_done < minimum_samples or job.elapsed_active_ms <= 0:
        return None, "estimating" if job.status is JobStatus.RUNNING else "unknown"
    per_unit_ms = job.elapsed_active_ms / job.units_done
    remaining = max(0, job.units_total - job.units_done)
    return round(per_unit_ms * remaining / 1000.0, 1), "estimated"


@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
def create_job(request: Request, body: EnqueueJobRequest) -> JobDetail:
    """Enqueue a job. Deduplicated: an equivalent active job is returned.

    Returns 201 for a newly created job and 200 when an existing equivalent
    one was adopted, so a double-click is visibly a no-op rather than a
    silent second scan (F-26).
    """
    with session_scope(_settings(request)) as session:
        job, created = enqueue_job(
            session,
            body.job_type,
            payload=body.payload,
            priority=body.priority,
            resource_class=body.resource_class,
            max_attempts=body.max_attempts,
        )
        session.flush()
        detail = JobDetail.model_validate(job)
        detail.eta_seconds, detail.eta_state = _estimate_eta(job)

    if not created:
        raise HTTPException(
            status_code=status.HTTP_200_OK,
            detail={"message": "An equivalent job is already active.", "job_id": str(detail.id)},
        ) from None
    return detail


def _act(request: Request, job_id: uuid.UUID, action: str) -> JobDetail:
    with session_scope(_settings(request)) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        try:
            if action == "pause":
                request_pause(session, job)
            elif action == "resume":
                resume_job(session, job)
            elif action == "cancel":
                request_cancel(session, job)
            elif action == "retry":
                retry_job(session, job)
        except ContinuumError as exc:
            # A guarded transition refused. Surface the reason, do not 500.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": exc.code,
                    "message": exc.user_message,
                    "remediation": exc.remediation,
                },
            ) from exc
        session.flush()
        detail = JobDetail.model_validate(job)
        detail.eta_seconds, detail.eta_state = _estimate_eta(job)
        return detail


@router.post("/{job_id}/pause", response_model=JobDetail)
def pause(request: Request, job_id: uuid.UUID) -> JobDetail:
    """Request a pause. Sets a flag; the worker stops between units."""
    return _act(request, job_id, "pause")


@router.post("/{job_id}/resume", response_model=JobDetail)
def resume(request: Request, job_id: uuid.UUID) -> JobDetail:
    return _act(request, job_id, "resume")


@router.post("/{job_id}/cancel", response_model=JobDetail)
def cancel(request: Request, job_id: uuid.UUID) -> JobDetail:
    """Request cancellation. Cooperative: never hard-kills the worker."""
    return _act(request, job_id, "cancel")


@router.post("/{job_id}/retry", response_model=JobDetail)
def retry(request: Request, job_id: uuid.UUID) -> JobDetail:
    return _act(request, job_id, "retry")


@router.get("/{job_id}/blocked-reason", response_model=dict)
def blocked_reason(request: Request, job_id: uuid.UUID) -> dict[str, object]:
    """Why a job is blocked and what the user can do about it (F-24)."""
    with session_scope(_settings(request)) as session:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job.status is not JobStatus.BLOCKED:
            return {"blocked": False}
        reason: BlockedReason | None = job.blocked_reason
        return {
            "blocked": True,
            "reason": reason.value if reason else None,
            "remediation": job.remediation or {},
        }
