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
