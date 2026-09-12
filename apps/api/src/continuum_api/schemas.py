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
    "AcquisitionActionResult",
    "AcquisitionOverview",
    "AcquisitionStatus",
    "AddSourceRequest",
    "DocumentStatus",
    "EnqueueJobRequest",
    "FamilyDetail",
    "FamilyProgress",
    "HealthResponse",
    "IntakeUnit",
    "IntakeView",
    "JobDetail",
    "JobEventOut",
    "JobStepOut",
    "JobSummary",
    "QueueItem",
    "ReadyResponse",
    "ReleaseEvent",
    "ReviewItem",
    "ScaffoldPlan",
    "SourceOut",
    "SourcesView",
    "UpdateAlert",
    "UpdateWatchItem",
    "UpdatesView",
    "WorkRow",
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


# ---------------------------------------------------------------------------
# Library acquisition
#
# The acquisition engine owns the rules and publishes JSON documents; these
# models are the stable shape the UI consumes. They are a projection, not a
# mirror: the engine can add fields without breaking this contract, and
# nothing franchise-specific is ever hardcoded here.
# ---------------------------------------------------------------------------
class DocumentStatus(BaseModel):
    name: str
    present: bool
    generated_at: str | None = None
    size_bytes: int = 0
    error: str | None = None


class AcquisitionStatus(BaseModel):
    """Whether acquisition is set up at all, and how fresh its data is."""

    configured: bool
    available: bool
    data_dir: str
    cli_available: bool
    cli_path: str = ""
    vault_root: str = ""
    generated_at: str | None = None
    documents: list[DocumentStatus] = Field(default_factory=list)


class FamilyProgress(BaseModel):
    """One source family: how much of it is actually in the library."""

    id: str
    title: str
    category: str | None = None
    medium: str | None = None
    path: str = ""
    folder_exists: bool = False
    works_total: int = 0
    complete: int = 0
    partial: int = 0
    missing: int = 0
    unknown: int = 0
    review: int = 0
    files: int = 0
    bytes: int = 0
    classes: list[str] = Field(default_factory=list)
    relations: dict[str, int] = Field(default_factory=dict)
    missing_folders: int = 0
    aliases: list[str] = Field(default_factory=list)


class WorkRow(BaseModel):
    """One work, with its classification and its local coverage."""

    id: str
    title: str
    canonical_title: str | None = None
    family_id: str
    family_title: str
    relation: str | None = None
    material_class: str | None = None
    medium: str | None = None
    edition: str | None = None
    official: bool | None = None
    authority: str | None = None
    origin: str | None = None
    confidence: str | None = None
    coverage_status: str | None = None
    coverage_reason: str | None = None
    layout_status: str | None = None
    local_path: str | None = None
    expected_path: str | None = None
    legacy_mapping: bool = False
    legacy_kind: str | None = None
    folder_exists: bool = False
    local_files: int = 0
    local_bytes: int = 0
    chapter_min: int | None = None
    chapter_max: int | None = None
    chapters: int = 0
    gaps: str = ""
    missing_chapters: str = ""
    remote_latest_chapter: float | None = None
    remote_volumes: int | None = None
    #: How many chapters the release itself says exist. Numbering is not
    #: dense - series skip integers and insert decimals - so the COUNT is
    #: what separates "the numbering jumps" from "something is missing".
    source_chapter_count: int | None = None
    languages: list[str] = Field(default_factory=list)
    unofficial_provenance: list[str] = Field(default_factory=list)
    review_required: bool = False
    contained_in: str | None = None
    aliases: list[str] = Field(default_factory=list)
    #: Exact titles to search a store or reader with (English first, then
    #: Japanese). The UI turns these into links; nothing is ever fetched.
    search_titles: list[str] = Field(default_factory=list)


class FamilyDetail(BaseModel):
    family: FamilyProgress
    works: list[WorkRow] = Field(default_factory=list)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class QueueItem(BaseModel):
    family: str
    family_id: str = ""
    work: str
    work_id: str
    relation: str | None = None
    material_class: str | None = None
    coverage_status: str | None = None
    reason: str | None = None
    best_source: str | None = None
    availability: str | None = None
    requires_purchase: str | None = None
    requires_user_action: bool = False
    downloadable: bool = False
    search_title: str | None = None
    url: str | None = None
    notes: str | None = None
    priority: int = 8
    source_hits: list[dict[str, Any]] = Field(default_factory=list)
    search_titles: list[str] = Field(default_factory=list)
    missing_chapters: str = ""
    chapters_held: int = 0
    chapters_total: int | None = None


class SourceOut(BaseModel):
    id: str
    name: str
    url: str = ""
    adapter: str = "web"
    enabled: bool = True
    capabilities: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)
    access: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    download_permitted: bool = False
    origin: str | None = None
    notes: str = ""
    search: str | None = None
    added_at: str | None = None
    tested_at: str | None = None
    test_ok: bool | None = None
    test_error: str | None = None
    test_checks: list[dict[str, Any]] = Field(default_factory=list)


class SourcesView(BaseModel):
    sources: list[SourceOut] = Field(default_factory=list)
    unofficial_hosts: list[str] = Field(default_factory=list)
    cli_available: bool = False
    capabilities: list[str] = Field(default_factory=list)
    adapters: list[str] = Field(default_factory=list)


class AddSourceRequest(BaseModel):
    """A source is a URL or a local folder the user points Continuum at."""

    url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)
    source_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    adapter: Literal["web", "local-folder", "bibliographic"] | None = None
    search: str | None = Field(default=None, max_length=2048)
    note: str | None = Field(default=None, max_length=500)
    download_permitted: bool = False
    test: bool = True
    #: How the source hands material over. Shown in the UI so the cost of a
    #: click is visible before the click.
    access: Literal[
        "FREE_OFFICIAL_WEB",
        "SUBSCRIPTION_WEB",
        "PAID_WEB",
        "DRM_EBOOK",
        "DRM_FREE_PURCHASE",
        "DIRECT_DOWNLOAD_AUTHORIZED",
        "LIBRARY_LENDING",
        "STREAMING",
        "PHYSICAL_ONLY",
    ] | None = None
    #: What this source is good for generally, so the engine can offer it as
    #: a fallback without naming it in code.
    roles: list[Literal["store-search-en", "store-search-ja", "anime-streaming"]] = Field(
        default_factory=list, max_length=3
    )


class AcquisitionActionResult(BaseModel):
    """What an action did, plus the command so it can be repeated by hand."""

    ok: bool
    message: str
    command: str = ""
    output: str = ""
    exit_code: int = 0


class IntakeUnit(BaseModel):
    source: str
    unit: str
    path: str
    files: int = 0
    classified_by: str | None = None
    series: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    unofficial_provenance: list[str] = Field(default_factory=list)
    colored: bool = False


class ReviewItem(BaseModel):
    kind: str
    family: str = ""
    item: str = ""
    detail: str = ""
    action: str = ""


class IntakeView(BaseModel):
    mode: str | None = None
    intake_dirs: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    units: list[IntakeUnit] = Field(default_factory=list)
    review: list[ReviewItem] = Field(default_factory=list)
    duplicates: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    proposed_moves: list[dict[str, Any]] = Field(default_factory=list)


class UpdateAlert(BaseModel):
    at: str | None = None
    kind: str = ""
    family: str = ""
    work: str | None = None
    source: str | None = None
    detail: str = ""


class UpdateWatchItem(BaseModel):
    family: str
    work: str
    work_id: str = ""
    relation: str | None = None
    latest_local: float | None = None
    latest_remote: float | None = None
    remote_volumes: int | None = None
    update_available: bool | None = None
    status: str | None = None
    last_checked: str | None = None
    source: str | None = None


class UpdatesView(BaseModel):
    generated_at: str | None = None
    last_check: str | None = None
    alerts: list[UpdateAlert] = Field(default_factory=list)
    items: list[UpdateWatchItem] = Field(default_factory=list)
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ScaffoldPlan(BaseModel):
    """Folders the library is missing. Creating them stays a CLI action."""

    counts: dict[str, int] = Field(default_factory=dict)
    create: list[dict[str, Any]] = Field(default_factory=list)
    review: list[dict[str, Any]] = Field(default_factory=list)
    command: str = ""
    ran: bool = False
    output: str = ""


class ReleaseEvent(BaseModel):
    """One dated thing that happened (or was seen) for a work.

    Two kinds, never mixed up: `published` is a real publication date from a
    bibliographic record, `detected` is when this machine noticed a change.
    Precision is carried explicitly because a legal-deposit record often
    gives only a year, and a calendar that invents a day is lying quietly.
    """

    date: str
    precision: Literal["day", "month", "year"] = "day"
    kind: Literal["published", "detected"] = "published"
    family: str = ""
    family_id: str = ""
    work: str = ""
    work_id: str = ""
    relation: str | None = None
    material_class: str | None = None
    detail: str = ""


class AcquisitionOverview(BaseModel):
    status: AcquisitionStatus
    totals: dict[str, int] = Field(default_factory=dict)
    relations: dict[str, int] = Field(default_factory=dict)
    families: list[FamilyProgress] = Field(default_factory=list)
    queue_preview: list[QueueItem] = Field(default_factory=list)
    alerts: list[UpdateAlert] = Field(default_factory=list)
    review_count: int = 0
    intake_pending: int = 0
    sources_enabled: int = 0
    sources_total: int = 0
