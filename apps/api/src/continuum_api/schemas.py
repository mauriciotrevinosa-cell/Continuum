"""API response/request schemas.

Separate Pydantic models rather than exposing ORM classes (D-06): the
database schema is the longest-lived asset in this product and must not be
shaped by API convenience. These are also the source of the generated
TypeScript client (D-10), so their shape is a contract.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from continuum_core import BlockedReason, JobStatus
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "EnqueueJobRequest",
    "HealthResponse",
    "JobDetail",
    "JobEventOut",
    "JobStepOut",
    "JobSummary",
    "ReadyResponse",
    "WorkerOut",
]


class HealthResponse(BaseModel):
    """Liveness plus enough non-secret context to diagnose Phase 0.

    Deliberately carries no configuration values that could contain a
    credential: the database URL is never included in any form.
    """

    status: Literal["ok"] = "ok"
    version: str
    phase: str = "0"
    api_host: str
    production_profile: str
    storage: dict[str, Any]
    providers: list[dict[str, Any]]


class ReadyResponse(BaseModel):
    """Readiness: whether dependencies this process needs are actually up."""

    ready: bool
    database: dict[str, Any]
    storage_healthy: bool
    migrations_current: bool | None = None
    detail: str | None = None


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: JobStatus
    blocked_reason: BlockedReason | None = None
    priority: int
    resource_class: str
    units_done: int
    units_total: int | None
    attempt: int
    max_attempts: int
    created_at: dt.datetime
    updated_at: dt.datetime
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None

    @property
    def progress_fraction(self) -> float | None:
        if not self.units_total:
            return None
        return self.units_done / self.units_total


class JobStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_key: str
    ordinal: int | None
    status: str
    attempt: int
    completed_at: dt.datetime | None = None


class JobEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    from_status: JobStatus | None = None
    to_status: JobStatus | None = None
    detail: dict[str, Any] | None = None
    created_at: dt.datetime


class JobDetail(JobSummary):
    """A job plus the state a user needs to act on it."""

    remediation: dict[str, Any] | None = None
    last_error: dict[str, Any] | None = None
    error_history: list[dict[str, Any]] = Field(default_factory=list)
    pause_requested: bool = False
    cancel_requested: bool = False
    lease_owner: uuid.UUID | None = None
    lease_expires_at: dt.datetime | None = None
    correlation_id: str | None = None
    hardware_signature: str | None = None
    elapsed_active_ms: int = 0
    #: None until enough samples exist. Displaying a confident wrong number
    #: is worse than saying "Estimating..." (Master Plan section 91.6).
    eta_seconds: float | None = None
    eta_state: Literal["estimating", "estimated", "unknown"] = "unknown"
    steps: list[JobStepOut] = Field(default_factory=list)
    recent_events: list[JobEventOut] = Field(default_factory=list)


class EnqueueJobRequest(BaseModel):
    """Enqueue a job.

    Note what is absent: there is no path parameter of any kind. No endpoint
    in Continuum accepts a filesystem path (F-50, A-03) -- such an endpoint is
    a directory-traversal machine no matter how carefully it validates.
    """

    job_type: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=-100, le=100)
    resource_class: str = Field(default="cpu", max_length=32)
    max_attempts: int = Field(default=5, ge=1, le=50)


class WorkerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hostname: str
    pid: int
    resource_classes: str
    hardware_signature: str | None
    started_at: dt.datetime
    last_heartbeat_at: dt.datetime
    drain_requested: bool
    stopped_at: dt.datetime | None
