/**
 * Thin typed client over the Phase 0 API.
 *
 * Hand-written for the Phase 0 surface. The generated OpenAPI types live in
 * `lib/api/generated/schema.d.ts` (`pnpm api:client`) and CI fails on drift
 * (D-10) -- generation needs a running API, so it is a CI step rather than a
 * build step.
 */

export const API_BASE = process.env.CONTINUUM_API_BASE ?? "http://127.0.0.1:8000";

export type JobStatus =
  | "QUEUED"
  | "BLOCKED"
  | "RUNNING"
  | "PAUSING"
  | "PAUSED"
  | "CANCELLING"
  | "CANCELLED"
  | "SUCCEEDED"
  | "FAILED_RETRYABLE"
  | "FAILED_FINAL";

export type BlockedReason =
  | "DEPENDENCY"
  | "MISSING_PROVIDER"
  | "MISSING_MODEL"
  | "MISSING_SOURCE_ASSET"
  | "AWAITING_APPROVAL"
  | "RESOURCE_UNAVAILABLE";

export interface JobSummary {
  id: string;
  job_type: string;
  status: JobStatus;
  blocked_reason: BlockedReason | null;
  priority: number;
  resource_class: string;
  units_done: number;
  units_total: number | null;
  attempt: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobStep {
  unit_key: string;
  ordinal: number | null;
  status: string;
  attempt: number;
  completed_at: string | null;
}

export interface JobEvent {
  event_type: string;
  from_status: JobStatus | null;
  to_status: JobStatus | null;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface JobDetail extends JobSummary {
  remediation: Record<string, unknown> | null;
  last_error: Record<string, unknown> | null;
  error_history: Record<string, unknown>[];
  pause_requested: boolean;
  cancel_requested: boolean;
  correlation_id: string | null;
  hardware_signature: string | null;
  elapsed_active_ms: number;
  eta_seconds: number | null;
  eta_state: "estimating" | "estimated" | "unknown";
  steps: JobStep[];
  recent_events: JobEvent[];
}

export interface HealthResponse {
  status: string;
  version: string;
  phase: string;
  api_host: string;
  production_profile: string;
  storage: {
    healthy: boolean;
    roots: { key: string; writable: boolean; exists: boolean; sync_provider: string | null }[];
    vault_protection: { status: string; detail: string; informational_only: boolean };
    sync_warnings: string[];
  };
  providers: { id: string; locality: string; cost_class: string; capabilities: string[] }[];
}

/** The API may simply not be running. Callers render that, they do not crash. */
export class ApiUnreachableError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiUnreachableError(
      `Cannot reach the Continuum API at ${API_BASE}. Start it with: uv run continuum-api`,
      { cause },
    );
  }
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  listJobs: (status?: JobStatus) =>
    request<JobSummary[]>(`/jobs${status ? `?status=${status}` : ""}`),
  getJob: (id: string) => request<JobDetail>(`/jobs/${id}`),
  pause: (id: string) => request<JobDetail>(`/jobs/${id}/pause`, { method: "POST" }),
  resume: (id: string) => request<JobDetail>(`/jobs/${id}/resume`, { method: "POST" }),
  cancel: (id: string) => request<JobDetail>(`/jobs/${id}/cancel`, { method: "POST" }),
  retry: (id: string) => request<JobDetail>(`/jobs/${id}/retry`, { method: "POST" }),
};

export function progressPercent(job: JobSummary): number | null {
  if (!job.units_total) return null;
  return Math.round((job.units_done / job.units_total) * 100);
}

export function formatEta(job: JobDetail): string {
  if (job.eta_state === "estimating") return "Estimating…";
  if (job.eta_seconds === null) return "—";
  const seconds = Math.round(job.eta_seconds);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/* ---------------------------------------------------------------------------
 * Library acquisition
 *
 * Acquisition belongs to the LIBRARY: what the user owns and what is missing
 * is true regardless of which project is open. Every shape here mirrors a
 * Pydantic model in the API; none of it carries library content at build
 * time, so an empty install renders an empty screen rather than a demo.
 * ------------------------------------------------------------------------- */

export interface DocumentStatus {
  name: string;
  present: boolean;
  generated_at: string | null;
  size_bytes: number;
  error: string | null;
}

/**
 * How one work stands in the Library.
 *
 * PRESENT is "in library" with nothing to compare against. NEEDS_MAPPING is
 * local material that is not matched to a work - never called missing.
 * STALE is a "missing" verdict about a folder that changed after the scan.
 */
export type LibraryState =
  | "COMPLETE"
  | "PARTIAL"
  | "PRESENT"
  | "MISSING"
  | "NEEDS_MAPPING"
  | "UNVERIFIED"
  | "STALE";

export type RollupState = LibraryState | "UNCATALOGUED" | "EMPTY";

export interface Freshness {
  state: "fresh" | "stale" | "unknown" | "empty";
  library_scanned_at: string | null;
  catalogue_refreshed_at: string | null;
  documents_generated_at: string | null;
  vault_changed: boolean | null;
  changed_families: string[];
  changed_folders: string[];
  unhashed_files: number | null;
  detail: string;
}

export interface AcquisitionStatus {
  configured: boolean;
  available: boolean;
  data_dir: string;
  cli_available: boolean;
  cli_path: string;
  vault_root: string;
  generated_at: string | null;
  documents: DocumentStatus[];
  freshness: Freshness;
  library_files: number;
  library_bytes: number;
}

export interface MaterialSummary {
  material_class: string;
  state: RollupState;
  story: boolean;
  works: number;
  complete: number;
  partial: number;
  present: number;
  missing: number;
  needs_mapping: number;
  unverified: number;
  stale: number;
  files: number;
  bytes: number;
  video_files: number;
  unmapped_files: number;
  last_added_at: string | null;
}

export interface EpisodeRun {
  season: number | null;
  episodes: number;
  episodes_text: string;
  gaps_text: string;
}

export interface FamilyProgress {
  id: string;
  title: string;
  category: string | null;
  medium: string | null;
  path: string;
  folder_exists: boolean;
  works_total: number;
  complete: number;
  partial: number;
  missing: number;
  unknown: number;
  review: number;
  files: number;
  bytes: number;
  classes: string[];
  relations: Record<string, number>;
  missing_folders: number;
  aliases: string[];
  state: RollupState;
  materials: MaterialSummary[];
  present: number;
  needs_mapping: number;
  story_works: number;
  story_held: number;
  supplements: number;
  supplements_held: number;
  attention: number;
  stale: boolean;
  last_added_at: string | null;
  origin: string;
  review_status: string;
}

export interface WorkRow {
  id: string;
  title: string;
  canonical_title: string | null;
  family_id: string;
  family_title: string;
  relation: string | null;
  material_class: string | null;
  medium: string | null;
  edition: string | null;
  official: boolean | null;
  authority: string | null;
  origin: string | null;
  confidence: string | null;
  coverage_status: string | null;
  coverage_reason: string | null;
  layout_status: string | null;
  local_path: string | null;
  expected_path: string | null;
  legacy_mapping: boolean;
  legacy_kind: string | null;
  folder_exists: boolean;
  local_files: number;
  local_bytes: number;
  chapter_min: number | null;
  chapter_max: number | null;
  chapters: number;
  gaps: string;
  missing_chapters: string;
  remote_latest_chapter: number | null;
  remote_volumes: number | null;
  source_chapter_count: number | null;
  languages: string[];
  unofficial_provenance: string[];
  review_required: boolean;
  contained_in: string | null;
  aliases: string[];
  search_titles: string[];
  state: LibraryState;
  story: boolean;
  media: "video" | "pages" | null;
  episodes: EpisodeRun[];
  other_videos: number;
  video_archives: number;
  contained_videos: number;
  archives_not_inventoried: number;
  unmapped_local_files: number;
  last_added_at: string | null;
}

export interface FamilyDetail {
  family: FamilyProgress;
  works: WorkRow[];
  findings: Record<string, unknown>[];
}

export interface QueueQuery {
  status?: string;
  family?: string;
  group?: string;
  q?: string;
  offset?: number;
  limit?: number;
}

/** One page of the queue, plus what the whole filtered set looks like. */
export interface QueuePage {
  total: number;
  offset: number;
  limit: number;
  by_status: Record<string, number>;
  needs_you: number;
  downloadable: number;
  items: QueueItem[];
  groups: QueueGroup[];
  needs_mapping: number;
}

export interface QueueItem {
  family: string;
  family_id: string;
  work: string;
  work_id: string;
  relation: string | null;
  material_class: string | null;
  coverage_status: string | null;
  reason: string | null;
  best_source: string | null;
  availability: string | null;
  requires_purchase: string | null;
  requires_user_action: boolean;
  downloadable: boolean;
  search_title: string | null;
  url: string | null;
  notes: string | null;
  priority: number;
  source_hits: Record<string, unknown>[];
  search_titles: string[];
  missing_chapters: string;
  chapters_held: number;
  chapters_total: number | null;
  state: LibraryState;
  group: string;
  story: boolean;
}

export interface QueueGroup {
  key: string;
  title: string;
  description: string;
  count: number;
  tone: Tone;
}

export type Tone = "ok" | "warn" | "err" | "info" | "muted" | "accent";

export interface SourceOut {
  id: string;
  name: string;
  url: string;
  adapter: string;
  enabled: boolean;
  capabilities: string[];
  operations: string[];
  access: string[];
  roles: string[];
  languages: string[];
  download_permitted: boolean;
  origin: string | null;
  notes: string;
  search: string | null;
  added_at: string | null;
  tested_at: string | null;
  test_ok: boolean | null;
  test_error: string | null;
  test_checks: { check?: string; ok?: boolean; detail?: string }[];
}

export interface SourcesView {
  sources: SourceOut[];
  unofficial_hosts: string[];
  cli_available: boolean;
  capabilities: string[];
  adapters: string[];
  /** The subset a browser may register: web sources, never a local folder. */
  browser_adapters: string[];
}

export interface AcquisitionActionResult {
  ok: boolean;
  message: string;
  command: string;
  output: string;
  exit_code: number;
}

export interface IntakeUnit {
  source: string;
  unit: string;
  path: string;
  files: number;
  action: string;
  section: "ready" | "identify" | "incomplete" | "known" | "conflict";
  family: string | null;
  work: string | null;
  classified_by: string | null;
  series: string[];
  languages: string[];
  unofficial_provenance: string[];
  colored: boolean;
}

export interface ReviewItem {
  kind: string;
  family: string;
  item: string;
  detail: string;
  action: string;
}

export interface IntakeView {
  mode: string | null;
  intake_dirs: string[];
  counts: Record<string, number>;
  units: IntakeUnit[];
  review: ReviewItem[];
  duplicates: Record<string, unknown>[];
  conflicts: Record<string, unknown>[];
  proposed_moves: Record<string, unknown>[];
}

export interface UpdateAlert {
  at: string | null;
  kind: string;
  family: string;
  work: string | null;
  source: string | null;
  detail: string;
}

export interface UpdateWatchItem {
  family: string;
  work: string;
  work_id: string;
  relation: string | null;
  latest_local: number | null;
  latest_remote: number | null;
  remote_volumes: number | null;
  update_available: boolean | null;
  status: string | null;
  last_checked: string | null;
  source: string | null;
}

export interface TimelineEvent {
  at: string | null;
  kind:
    | "new_chapters"
    | "new_volumes"
    | "new_release"
    | "source_changed"
    | "local_files"
    | "coverage"
    | "other";
  title: string;
  detail: string;
  family: string;
  family_id: string;
  work: string | null;
  material_class: string | null;
}

export interface UpdatesView {
  generated_at: string | null;
  last_check: string | null;
  alerts: UpdateAlert[];
  items: UpdateWatchItem[];
  sources: Record<string, Record<string, unknown>>;
  timeline: TimelineEvent[];
}

export interface ScaffoldPlan {
  counts: Record<string, number>;
  create: Record<string, unknown>[];
  review: Record<string, unknown>[];
  command: string;
  ran: boolean;
  output: string;
}

export interface ReleaseEvent {
  date: string;
  precision: "day" | "month" | "year";
  kind: "published" | "detected";
  family: string;
  family_id: string;
  work: string;
  work_id: string;
  relation: string | null;
  material_class: string | null;
  detail: string;
}

export interface LibraryHero {
  families: number;
  bytes: number;
  files: number;
  story_works: number;
  complete: number;
  partial: number;
  present: number;
  missing: number;
  needs_mapping: number;
  unverified: number;
  stale: number;
  complete_families: number;
  attention_families: number;
}

export interface RecentAddition {
  family_id: string;
  family: string;
  material_class: string;
  files: number;
  bytes: number;
  video_files: number;
  last_added_at: string;
  state: string;
}

export interface NextStep {
  kind: "refresh" | "map" | "finish" | "update" | "acquire" | "intake" | "review";
  title: string;
  detail: string;
  family_id: string;
  work_id: string;
  tone: Tone;
}

export interface AcquisitionOverview {
  hero: LibraryHero;
  recently_added: RecentAddition[];
  next_steps: NextStep[];
  status: AcquisitionStatus;
  totals: Record<string, number>;
  relations: Record<string, number>;
  families: FamilyProgress[];
  queue_preview: QueueItem[];
  alerts: UpdateAlert[];
  review_count: number;
  intake_pending: number;
  sources_enabled: number;
  sources_total: number;
}

/* ---------------------------------------------------------------------------
 * Held media: opened by opaque id, never by path (F-50)
 * ------------------------------------------------------------------------- */

export interface MediaStatus {
  available: boolean;
  reason: string;
}

export interface ContainedVideo {
  name: string;
  size_bytes: number;
  season: number | null;
  episode: number | null;
}

export interface MediaUnit {
  id: string;
  name: string;
  kind: string;
  view: "pages" | "video" | "document" | "image" | "bundle" | "mixed" | "none";
  size_bytes: number;
  label: string;
  season: number | null;
  episode: number | null;
  chapters: number;
  chapter_text: string;
  volumes: number[];
  pages: number;
  contained_videos: number;
  contained: ContainedVideo[];
  plays_in_browser: "yes" | "maybe" | "no";
}

export interface WorkMedia {
  available: boolean;
  reason: string;
  work_id: string;
  title: string;
  family_id: string;
  family_title: string;
  material_class: string | null;
  relation: string | null;
  state: LibraryState;
  coverage_reason: string;
  unmapped: boolean;
  units: MediaUnit[];
}

export interface MediaDetail {
  unit: MediaUnit;
  work_id: string;
  work_title: string;
  family_id: string;
  family_title: string;
  material_class: string | null;
  position: number;
  total: number;
  previous_id: string | null;
  next_id: string | null;
}

export interface ArchiveListing {
  pages: { index: number; label: string; chapter: string }[];
  chapters: { label: string; first: number; count: number }[];
  videos: ContainedVideo[];
  other_entries: number;
}

/** What an opaque media id looks like; anything else never leaves the browser. */
export const MEDIA_ID = /^m1_[0-9a-f]{32}$/;

export const media = {
  status: () => request<MediaStatus>("/library/media/status"),
  forWork: (workId: string) =>
    request<WorkMedia>(`/library/media?work=${encodeURIComponent(workId)}`),
  unmatched: (familyId: string, material: string) =>
    request<WorkMedia>(
      `/library/media?family=${encodeURIComponent(familyId)}&material=${encodeURIComponent(material)}`,
    ),
  detail: (id: string) => request<MediaDetail>(`/library/media/${encodeURIComponent(id)}`),
  pages: (id: string) => request<ArchiveListing>(`/library/media/${encodeURIComponent(id)}/pages`),
};

/* ---------------------------------------------------------------------------
 * Projects: creative work made inside Continuum
 * ------------------------------------------------------------------------- */

export type DocumentLifecycle =
  | "IDEA"
  | "DRAFT"
  | "REVIEW"
  | "APPROVED"
  | "LOCKED"
  | "SUPERSEDED"
  | "ARCHIVED"
  | "UNFILED";

export interface ProjectDocument {
  id: string;
  title: string;
  category: string;
  section: "story" | "production" | "reference" | "extra";
  lifecycle: DocumentLifecycle;
  version: string | null;
  lineage: string | null;
  supersedes: string | null;
  superseded_by: string | null;
  derived_from: string | null;
  episode: string | null;
  summary: string;
  author_status: string | null;
  dated: string | null;
  modified_at: string | null;
  size_bytes: number;
  filed: boolean;
  constraints: string[];
  /** How developed the document is, as the manifest records it. */
  maturity: "ROUGH" | "DETAILED" | "PRODUCTION_READY" | null;
  /** RULE, CORRECTION, INDEX or CONTENT, as the manifest records it. */
  authority: "CONTENT" | "RULE" | "CORRECTION" | "INDEX";
  /** Parts of other documents this one overrides, as the documents state it. */
  overrides: { document: string; scope: string }[];
  overridden_by: { document: string; scope: string }[];
  /** Registered by an explicit manifest entry, by a manifest convention, or not at all. */
  registration: "explicit" | "convention" | "unfiled";
  convention: string | null;
  /** Small values the manifest reads from the document's head (pages, title). */
  facts: Record<string, string>;
  /** The commit that last changed the document, for projects read from Git. */
  commit: string | null;
  /** The approved milestone this in-review document has since been resolved by. */
  resolved_by: string | null;
  /** What the document applies to beyond one episode: season:<n> or project. */
  applies_to: string | null;
}

/** Where a project was read from. A Git source names its ref and commit, never a path. */
export interface ProjectSource {
  kind: "directory" | "git";
  ref: string | null;
  directory: string | null;
  commit: string | null;
  committed_at: string | null;
  subject: string | null;
}

export interface EpisodeLevel {
  id: string;
  label: string;
  requires: string[];
  state: string | null;
  count_pages: boolean;
}

export interface EpisodeStanding {
  code: string;
  season: number | null;
  number: number | null;
  title: string | null;
  level: string | null;
  label: string;
  state: string | null;
  pages: number | null;
  documents: { category: string; id: string; title: string; lifecycle: DocumentLifecycle; resolved_by: string | null }[];
  missing: string[];
  last_commit: string | null;
  last_changed_at: string | null;
  /** Every named page count (base panelization, integrated provisional...). */
  page_counts: { id: string; label: string; pages: number; document_id: string }[];
  /** Which count `pages` is. */
  current_count: string | null;
  /** The ordered documents a chapter package for this episode is built from. */
  sources: EpisodeSource[];
  missing_sources: string[];
}

export interface EpisodeSource {
  role: string;
  label: string;
  document_id: string;
  title: string;
  lifecycle: DocumentLifecycle;
  commit: string | null;
  required: boolean;
  when: string;
}

export interface EpisodeBoardSummary {
  episodes: number;
  by_level: Record<string, number>;
  /** Current pages. */
  pages: number;
  unmet: number;
  page_totals: { id: string; label: string; pages: number; episodes: number; current: boolean }[];
}

export interface ProjectResync {
  project_id: string;
  fetched: boolean;
  previous_commit: string | null;
  commit: string | null;
  changed: boolean;
  detail: string;
  source: ProjectSource;
}

export interface PipelineStage {
  id: string;
  title: string;
  track: string;
  description: string;
  artifacts: number;
}

export interface ProjectSummary {
  id: string;
  title: string;
  kind: string;
  logline: string;
  status: string;
  documents: number;
  approved: number;
  in_progress: number;
  extras: number;
  updated_at: string | null;
  warnings: string[];
  source: ProjectSource;
}

export interface ProjectDetail {
  project: ProjectSummary;
  description: string;
  documents: ProjectDocument[];
  pipeline: PipelineStage[];
  counts: Record<string, number>;
  levels: EpisodeLevel[];
  episodes: EpisodeStanding[];
  episode_summary: EpisodeBoardSummary;
}

export interface ProjectDocumentBody {
  project: ProjectSummary;
  document: ProjectDocument;
  markdown: string;
  versions: ProjectDocument[];
}

export const projects = {
  list: () => request<ProjectSummary[]>("/projects"),
  detail: (id: string) => request<ProjectDetail>(`/projects/${encodeURIComponent(id)}`),
  document: (id: string, documentId: string) =>
    request<ProjectDocumentBody>(
      `/projects/${encodeURIComponent(id)}/documents/${encodeURIComponent(documentId)}`,
    ),
};

/** How a source hands material over. Mirrors the engine's access models. */
export type AccessModel =
  | "FREE_OFFICIAL_WEB"
  | "SUBSCRIPTION_WEB"
  | "PAID_WEB"
  | "DRM_EBOOK"
  | "DRM_FREE_PURCHASE"
  | "DIRECT_DOWNLOAD_AUTHORIZED"
  | "LIBRARY_LENDING"
  | "STREAMING"
  | "PHYSICAL_ONLY";

export const ACCESS_MODELS: readonly AccessModel[] = [
  "FREE_OFFICIAL_WEB",
  "SUBSCRIPTION_WEB",
  "PAID_WEB",
  "DRM_EBOOK",
  "DRM_FREE_PURCHASE",
  "DIRECT_DOWNLOAD_AUTHORIZED",
  "LIBRARY_LENDING",
  "STREAMING",
  "PHYSICAL_ONLY",
];

export type SourceRole = "store-search-en" | "store-search-ja" | "anime-streaming";

export interface AddSourceBody {
  url: string;
  name?: string | null;
  source_id?: string | null;
  adapter?: "web" | "bibliographic" | null;
  search?: string | null;
  note?: string | null;
  access?: AccessModel | null;
  roles?: SourceRole[];
  download_permitted?: boolean;
  test?: boolean;
}

const ACQ = "/library/acquisition";

export const acquisition = {
  overview: () => request<AcquisitionOverview>(ACQ),
  families: () => request<FamilyProgress[]>(`${ACQ}/families`),
  family: (id: string) => request<FamilyDetail>(`${ACQ}/families/${encodeURIComponent(id)}`),
  queue: (params: QueueQuery = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    const qs = search.toString();
    return request<QueuePage>(`${ACQ}/queue${qs ? `?${qs}` : ""}`);
  },
  sources: () => request<SourcesView>(`${ACQ}/sources`),
  intake: () => request<IntakeView>(`${ACQ}/intake`),
  updates: () => request<UpdatesView>(`${ACQ}/updates`),
  status: () => request<AcquisitionStatus>(`${ACQ}/status`),
  refresh: () => request<AcquisitionActionResult>(`${ACQ}/refresh`, { method: "POST" }),
  calendar: () => request<ReleaseEvent[]>(`${ACQ}/calendar`),
  scaffold: () => request<ScaffoldPlan>(`${ACQ}/scaffold`),
  refreshScaffold: () => request<ScaffoldPlan>(`${ACQ}/scaffold/plan`, { method: "POST" }),
  refreshIntake: () => request<AcquisitionActionResult>(`${ACQ}/intake/refresh`, { method: "POST" }),
  addSource: (body: AddSourceBody) =>
    request<AcquisitionActionResult>(`${ACQ}/sources`, { method: "POST", body: JSON.stringify(body) }),
  sourceAction: (id: string, action: "test" | "enable" | "disable" | "remove") =>
    request<AcquisitionActionResult>(`${ACQ}/sources/${encodeURIComponent(id)}/${action}`, {
      method: "POST",
    }),
};
