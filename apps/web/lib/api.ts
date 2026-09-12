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

export interface AcquisitionStatus {
  configured: boolean;
  available: boolean;
  data_dir: string;
  cli_available: boolean;
  cli_path: string;
  vault_root: string;
  generated_at: string | null;
  documents: DocumentStatus[];
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
}

export interface FamilyDetail {
  family: FamilyProgress;
  works: WorkRow[];
  findings: Record<string, unknown>[];
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
}

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

export interface UpdatesView {
  generated_at: string | null;
  last_check: string | null;
  alerts: UpdateAlert[];
  items: UpdateWatchItem[];
  sources: Record<string, Record<string, unknown>>;
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

export interface AcquisitionOverview {
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
  adapter?: "web" | "local-folder" | "bibliographic" | null;
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
  queue: (status?: string) =>
    request<QueueItem[]>(`${ACQ}/queue${status ? `?status=${encodeURIComponent(status)}` : ""}`),
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
