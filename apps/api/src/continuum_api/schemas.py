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
from urllib.parse import urlsplit

from continuum_core import BlockedReason, JobStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "AcquisitionActionResult",
    "AcquisitionOverview",
    "AcquisitionStatus",
    "AddSourceRequest",
    "ArchiveListingOut",
    "ArchivePageOut",
    "ChapterGroup",
    "ContainedVideo",
    "DocumentStatus",
    "EnqueueJobRequest",
    "EpisodeRun",
    "FamilyDetail",
    "FamilyProgress",
    "Freshness",
    "HealthResponse",
    "IntakeUnit",
    "IntakeView",
    "JobDetail",
    "JobEventOut",
    "JobStepOut",
    "JobSummary",
    "LibraryHero",
    "MaterialSummary",
    "MediaDetail",
    "MediaStatus",
    "MediaUnit",
    "NextStep",
    "PipelineStage",
    "ProjectDetail",
    "ProjectDocumentBody",
    "ProjectDocumentOut",
    "ProjectSummary",
    "QueueGroup",
    "QueueItem",
    "QueuePage",
    "ReadyResponse",
    "RecentAddition",
    "ReleaseEvent",
    "ReviewItem",
    "ScaffoldPlan",
    "SourceOut",
    "SourcesView",
    "TimelineEvent",
    "UpdateAlert",
    "UpdateWatchItem",
    "UpdatesView",
    "WorkMedia",
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


#: How one work stands in the library, in the words the screens use.
#:
#: COMPLETE / PARTIAL come from the engine's comparison with what exists.
#: PRESENT is held with nothing to compare against ("in library").
#: NEEDS_MAPPING is local material the engine could not attribute - it may
#: well be this work, so it is never called missing.
#: UNVERIFIED is a work whose existence or coverage is not established.
#: STALE is a MISSING verdict about a family whose folder changed after the
#: scan: a claim of absence from an out-of-date report is not repeated.
LibraryState = Literal[
    "COMPLETE", "PARTIAL", "PRESENT", "MISSING", "NEEDS_MAPPING", "UNVERIFIED", "STALE"
]


class Freshness(BaseModel):
    """How current the documents are, stated in three independent clocks."""

    #: fresh: the Vault is unchanged since the scan. stale: it changed.
    #: unknown: it could not be checked. empty: there is no scan at all.
    state: Literal["fresh", "stale", "unknown", "empty"] = "empty"
    library_scanned_at: str | None = None
    catalogue_refreshed_at: str | None = None
    documents_generated_at: str | None = None
    vault_changed: bool | None = None
    #: Families whose folder changed after the scan (ids).
    changed_families: list[str] = Field(default_factory=list)
    #: Top-level folders that changed and belong to no family yet.
    changed_folders: list[str] = Field(default_factory=list)
    #: Files the last scan did not hash, so duplicate detection trails them.
    unhashed_files: int | None = None
    detail: str = ""


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
    freshness: Freshness = Field(default_factory=Freshness)
    library_files: int = 0
    library_bytes: int = 0


class MaterialSummary(BaseModel):
    """One kind of material within a family: what is held and what is not."""

    material_class: str
    #: The class rolled up. UNCATALOGUED: local media with no work to own it.
    state: LibraryState | Literal["UNCATALOGUED", "EMPTY"]
    story: bool = False
    works: int = 0
    complete: int = 0
    partial: int = 0
    present: int = 0
    missing: int = 0
    needs_mapping: int = 0
    unverified: int = 0
    stale: int = 0
    files: int = 0
    bytes: int = 0
    video_files: int = 0
    #: Media in this class folder that no work owns.
    unmapped_files: int = 0
    last_added_at: str | None = None


class EpisodeRun(BaseModel):
    """Episodes of one season, as the file names state them."""

    season: int | None = None
    episodes: int = 0
    episodes_text: str = ""
    gaps_text: str = ""


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
    state: LibraryState | Literal["UNCATALOGUED", "EMPTY"] = "EMPTY"
    materials: list[MaterialSummary] = Field(default_factory=list)
    present: int = 0
    needs_mapping: int = 0
    story_works: int = 0
    story_held: int = 0
    supplements: int = 0
    supplements_held: int = 0
    #: Things to act on: partial or unmapped works, stale verdicts, missing
    #: main-line story works. Catalogue suggestions are counted in `review`.
    attention: int = 0
    stale: bool = False
    last_added_at: str | None = None
    origin: str = "curated"
    review_status: str = "ACCEPTED"


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
    state: LibraryState = "UNVERIFIED"
    story: bool = False
    media: Literal["video", "pages"] | None = None
    episodes: list[EpisodeRun] = Field(default_factory=list)
    other_videos: int = 0
    #: Archives are containers. How many of the work's files are archives
    #: holding video, how many videos they hold, and how many archives have
    #: not been inventoried - so a file count is never read as episodes.
    video_archives: int = 0
    contained_videos: int = 0
    archives_not_inventoried: int = 0
    unmapped_local_files: int = 0
    last_added_at: str | None = None
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
    state: LibraryState = "MISSING"
    group: str = ""
    story: bool = False


class QueueGroup(BaseModel):
    """A reason to acquire something, with how many works share it."""

    key: str
    title: str
    description: str = ""
    count: int = 0
    tone: Literal["ok", "warn", "err", "info", "muted", "accent"] = "muted"


class QueuePage(BaseModel):
    """A window onto the queue, plus what the whole filtered set looks like."""

    total: int = 0
    offset: int = 0
    limit: int = 50
    #: Counts across the UNFILTERED queue, so the filter buttons can say how
    #: much each one would show before it is clicked.
    by_status: dict[str, int] = Field(default_factory=dict)
    needs_you: int = 0
    downloadable: int = 0
    items: list[QueueItem] = Field(default_factory=list)
    groups: list[QueueGroup] = Field(default_factory=list)
    #: Works that may already be in the library under another folder: mapping
    #: them is the step before buying anything.
    needs_mapping: int = 0


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
    #: Every adapter the model knows, for rendering what is registered.
    adapters: list[str] = Field(default_factory=list)
    #: The subset a browser may register. Local folders are absent by
    #: design (F-50) and arrive through the local tooling instead.
    browser_adapters: list[str] = Field(default_factory=list)


class AddSourceRequest(BaseModel):
    """A web source the user points Continuum at.

    Web only, deliberately. A local folder is a raw filesystem path, and the
    Phase 0 API takes none from a client (F-50) - naming the field `url` would
    not change what it carries. Local-folder sources stay supported in the
    model and are registered by the local tooling, which writes the same
    registry; the browser then reads and shows them like any other source.
    """

    url: str = Field(min_length=1, max_length=2048)
    name: str | None = Field(default=None, max_length=200)
    source_id: str | None = Field(default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    adapter: Literal["web", "bibliographic"] | None = None
    search: str | None = Field(default=None, max_length=2048)
    note: str | None = Field(default=None, max_length=500)
    download_permitted: bool = False
    test: bool = True

    #: How the source hands material over. Shown in the UI so the cost of a
    #: click is visible before the click.
    @field_validator("url")
    @classmethod
    def _must_be_a_web_url(cls, value: str) -> str:
        """Accept http(s) only: no filesystem path enters through a browser.

        Rejecting by scheme alone is not enough - a Windows path, a UNC share
        and a bare absolute path carry no scheme at all, and `file:` is a
        filesystem path wearing a URL costume.
        """
        candidate = value.strip()
        parsed = urlsplit(candidate)
        if parsed.scheme.lower() in ("http", "https") and parsed.netloc:
            return candidate
        raise ValueError(
            "a source registered from the browser must be an http:// or https:// address. "
            "Local folders are registered with the acquisition CLI "
            "(sources add <folder>), which writes the same registry."
        )

    access: (
        Literal[
            "FREE_OFFICIAL_WEB",
            "SUBSCRIPTION_WEB",
            "PAID_WEB",
            "DRM_EBOOK",
            "DRM_FREE_PURCHASE",
            "DIRECT_DOWNLOAD_AUTHORIZED",
            "LIBRARY_LENDING",
            "STREAMING",
            "PHYSICAL_ONLY",
        ]
        | None
    ) = None
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
    #: What the importer decided (or would decide, in a dry run).
    action: str = ""
    #: ready | identify | incomplete | known | conflict
    section: str = "identify"
    family: str | None = None
    work: str | None = None
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


class TimelineEvent(BaseModel):
    """One thing that changed, in the order it happened."""

    at: str | None = None
    kind: Literal[
        "new_chapters",
        "new_volumes",
        "new_release",
        "source_changed",
        "local_files",
        "coverage",
        "other",
    ] = "other"
    title: str = ""
    detail: str = ""
    family: str = ""
    family_id: str = ""
    work: str | None = None
    material_class: str | None = None


class UpdatesView(BaseModel):
    generated_at: str | None = None
    last_check: str | None = None
    alerts: list[UpdateAlert] = Field(default_factory=list)
    items: list[UpdateWatchItem] = Field(default_factory=list)
    sources: dict[str, dict[str, Any]] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)


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


class LibraryHero(BaseModel):
    """The first thing the Library says about itself."""

    families: int = 0
    bytes: int = 0
    files: int = 0
    story_works: int = 0
    complete: int = 0
    partial: int = 0
    present: int = 0
    missing: int = 0
    needs_mapping: int = 0
    unverified: int = 0
    stale: int = 0
    complete_families: int = 0
    attention_families: int = 0


class RecentAddition(BaseModel):
    """A kind of material in a family that received files recently."""

    family_id: str
    family: str
    material_class: str
    files: int = 0
    bytes: int = 0
    video_files: int = 0
    last_added_at: str
    state: str = ""


class NextStep(BaseModel):
    """One useful thing to do next, in plain words."""

    kind: Literal["refresh", "map", "finish", "update", "acquire", "intake", "review"]
    title: str
    detail: str = ""
    family_id: str = ""
    work_id: str = ""
    tone: Literal["ok", "warn", "err", "info", "muted", "accent"] = "muted"


class MediaStatus(BaseModel):
    """Whether held media can be opened on this machine, and why not."""

    available: bool
    reason: str = ""


class ContainedVideo(BaseModel):
    """A video inside an archive. Listed, never streamed from the archive."""

    name: str
    size_bytes: int = 0
    season: int | None = None
    episode: int | None = None


class MediaUnit(BaseModel):
    """One openable file of a work, addressed by an opaque id."""

    id: str
    name: str
    kind: str
    #: pages: an image archive; video: a playable file; document: a PDF;
    #: bundle: an archive of videos; none: held, but not previewable.
    view: Literal["pages", "video", "document", "bundle", "none"]
    size_bytes: int = 0
    label: str = ""
    season: int | None = None
    episode: int | None = None
    chapters: int = 0
    chapter_text: str = ""
    volumes: list[int] = Field(default_factory=list)
    pages: int = 0
    contained_videos: int = 0
    contained: list[ContainedVideo] = Field(default_factory=list)
    #: yes: plays in every modern browser; maybe: depends on the codecs.
    plays_in_browser: Literal["yes", "maybe", "no"] = "no"


class WorkMedia(BaseModel):
    available: bool = False
    reason: str = ""
    work_id: str = ""
    title: str = ""
    family_id: str = ""
    family_title: str = ""
    material_class: str | None = None
    relation: str | None = None
    state: LibraryState = "UNVERIFIED"
    coverage_reason: str = ""
    unmapped: bool = False
    units: list[MediaUnit] = Field(default_factory=list)


class MediaDetail(BaseModel):
    unit: MediaUnit
    work_id: str = ""
    work_title: str = ""
    family_id: str = ""
    family_title: str = ""
    material_class: str | None = None
    position: int = -1
    total: int = 0
    previous_id: str | None = None
    next_id: str | None = None


class ArchivePageOut(BaseModel):
    index: int
    label: str
    chapter: str = ""


class ChapterGroup(BaseModel):
    label: str
    first: int
    count: int


class ArchiveListingOut(BaseModel):
    pages: list[ArchivePageOut] = Field(default_factory=list)
    chapters: list[ChapterGroup] = Field(default_factory=list)
    videos: list[ContainedVideo] = Field(default_factory=list)
    other_entries: int = 0


#: Where a project document stands. APPROVED and LOCKED are continuity; the
#: states before them are work in progress; SUPERSEDED and ARCHIVED are
#: history. UNFILED is a document the project's manifest does not register.
DocumentLifecycle = Literal[
    "IDEA", "DRAFT", "REVIEW", "APPROVED", "LOCKED", "SUPERSEDED", "ARCHIVED", "UNFILED"
]


class ProjectDocumentOut(BaseModel):
    id: str
    title: str
    category: str
    section: Literal["story", "production", "reference", "extra"]
    lifecycle: DocumentLifecycle
    version: str | None = None
    lineage: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    derived_from: str | None = None
    episode: str | None = None
    summary: str = ""
    #: The author's own words about the document's standing. Informational;
    #: never the source of ``lifecycle``.
    author_status: str | None = None
    dated: str | None = None
    modified_at: str | None = None
    size_bytes: int = 0
    filed: bool = True
    constraints: list[str] = Field(default_factory=list)


class PipelineStage(BaseModel):
    id: str
    title: str
    track: str = "story"
    description: str = ""
    #: Artifacts produced for this stage so far. Documents count where their
    #: category names the stage; generated artifacts arrive in later phases.
    artifacts: int = 0


class ProjectSummary(BaseModel):
    id: str
    title: str
    kind: str
    logline: str = ""
    status: str = "active"
    documents: int = 0
    approved: int = 0
    # Unapproved work on the story or its production; notes and references are extras.
    in_progress: int = 0
    extras: int = 0
    updated_at: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ProjectDetail(BaseModel):
    project: ProjectSummary
    description: str = ""
    documents: list[ProjectDocumentOut] = Field(default_factory=list)
    pipeline: list[PipelineStage] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class ProjectDocumentBody(BaseModel):
    project: ProjectSummary
    document: ProjectDocumentOut
    markdown: str
    versions: list[ProjectDocumentOut] = Field(default_factory=list)


class AcquisitionOverview(BaseModel):
    hero: LibraryHero = Field(default_factory=LibraryHero)
    recently_added: list[RecentAddition] = Field(default_factory=list)
    next_steps: list[NextStep] = Field(default_factory=list)
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
