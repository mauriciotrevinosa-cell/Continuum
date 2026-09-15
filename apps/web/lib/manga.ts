/**
 * Page-by-page manga production and the character reference corpus, as the
 * studio sees them.
 *
 * Shapes mirror the dictionaries assembled by continuum_api.routers.manga and
 * continuum_api.routers.corpus. Server components read through `manga`
 * (direct to the API); client components act through `vaultFetch`, which goes
 * through the allowlisted /vault-api passage.
 */

import { API_BASE, ApiUnreachableError } from "./api";
import { VaultNotFound } from "./vault";

export type PageState = "WAITING" | "BLOCKED" | "READY" | "IN_REVIEW" | "APPROVED" | "STALE";
export type Finish = "COMPOSITION_MASTER" | "BW_FINISH" | "COLOR_FINISH";
export const FINISHES: { kind: Finish; label: string }[] = [
  { kind: "COMPOSITION_MASTER", label: "Master" },
  { kind: "BW_FINISH", label: "B&W" },
  { kind: "COLOR_FINISH", label: "Color" },
];

export interface Reason {
  kind: string;
  key?: string;
  detail?: string;
  old?: string;
  new?: string;
}

export interface Profile {
  id: string;
  name: string;
  version: number;
  status: "DRAFT" | "PROMOTED" | "RETIRED";
  body: Record<string, unknown>;
  hash: string;
  promoted_from_run: string | null;
}

export interface PageSummary {
  id: string;
  sequence: number;
  page_key: string;
  integrated_page: number | null;
  label: string | null;
  state: PageState;
  reasons: Reason[];
  approved_attempt_id: string | null;
  latest_attempt_id: string | null;
  attempt_count: number;
  images: Record<Finish, string> | null;
}

export interface ApprovedPage {
  sequence: number;
  page_key: string;
  attempt_id: string;
  master_sha256: string;
  output_class: string | null;
}

export interface RunView {
  id: string;
  project_key: string;
  episode: string;
  chapter: number | null;
  purpose: "NON_CANON_SAMPLE" | "PRODUCTION";
  status: "OPEN" | "SAMPLE_PASSED" | "SAMPLE_FAILED" | "CLOSED";
  decision_notes: string;
  profile: Profile;
  continuity: {
    id: string;
    version: number;
    reason: string;
    body: { approved_pages: ApprovedPage[]; character_rules: Record<string, unknown> };
  };
  next_page_id: string | null;
  pages: PageSummary[];
}

export interface RunListItem {
  id: string;
  episode: string;
  chapter: number | null;
  purpose: RunView["purpose"];
  status: RunView["status"];
  created_at: string;
  profile: { name: string; version: number } | null;
  pages: number;
  states: Partial<Record<PageState, number>>;
}

export interface Dialogue {
  speaker: string;
  kind: string;
  text: string;
}

export interface Lineage {
  document_id?: string;
  version?: string | null;
  commit?: string | null;
  content_hash?: string;
  base_page?: number;
  overlay?: { document_id: string; version?: string | null; commit?: string | null; item_key?: string } | null;
  [key: string]: unknown;
}

export interface PageBody {
  page_key: string;
  label: string | null;
  scene: string | null;
  base_page: number | null;
  integrated_page: number | null;
  directions: string[];
  dialogue: Dialogue[];
  constraints: string[];
  characters: string[];
  intents: string[];
  origin: "base" | "overlay";
  chapter_end: boolean;
  lineage: Lineage;
  insertion?: { item_key: string; text?: string; source_beats?: { number: number; title: string }[] } | null;
}

export interface Observation {
  id: string;
  character_id: string;
  locator: string;
  source_kind: "CURATED" | "SOURCE_PAGE" | "FAN_ART" | "APPROVED_OUTPUT";
  reference_id: string | null;
  unit_key: string | null;
  page_offset: number | null;
  series_key: string | null;
  source_label: string;
  authority: string;
  status: "CANDIDATE" | "CONFIRMED" | "REJECTED";
  role: "GROUNDING" | "STYLIZATION" | "EVIDENCE";
  anchor: boolean;
  atypical: boolean;
  facets: string[];
  angle: string | null;
  framing: string | null;
  expression: string;
  pose: string;
  evidence: Record<string, unknown>;
  notes: string;
  reviewed: boolean;
  image: string;
  score?: number;
  why?: string[];
}

export interface ReadinessGroup {
  state: "READY" | "PARTIAL" | "MISSING";
  confirmed_high_authority: number;
  distinct_sources: number;
  angles: string[];
  project_created: number;
  missing_angles?: string[];
}

export interface CorpusReadiness {
  grounded: boolean;
  ungrounded: string[];
  groups: Record<string, ReadinessGroup>;
}

export interface BundleCharacter {
  name: string;
  character_id: string;
  readiness: CorpusReadiness;
  need: { facets: string[]; framing: string | null; angles: string[]; expressions: string[]; poses: string[]; with: string[] };
  observations: Observation[];
  stylization_observations: Observation[];
  available_observations: number;
  forbidden: string[];
  rules: Record<string, unknown>;
}

export interface GrammarRef {
  locator: string;
  series_key: string;
  label: string;
  score: number;
  teaches: string[];
  structure: { panel_count: number; largest_panel_share: number; negative_space: number; ink_density: number };
}

export interface EnvironmentRef {
  reference_id: string;
  locator: string;
  label: string;
  origin: string;
  matched: string[];
  teaches: string[];
}

export interface PageBundle {
  page: PageBody;
  profile: { id: string; name: string; version: number; hash: string };
  continuity: { id: string; version: number; approved_pages: ApprovedPage[]; character_rules: Record<string, unknown> };
  characters: BundleCharacter[];
  grammar: GrammarRef[];
  environment: EnvironmentRef[];
  gaps: string[];
}

export interface PageAttempt {
  id: string;
  attempt: number;
  state: string;
  display_state: string;
  output_class: string | null;
  test_only: boolean;
  allowed_decisions: string[];
  seed: number | null;
  created_at: string | null;
  generated_at: string | null;
  parent_attempt_id: string | null;
  job: {
    status: string;
    blocked_reason: string | null;
    remediation: string | null;
    error: string | null;
    error_remediation: string | null;
  } | null;
  artwork_provenance: Record<string, unknown>;
  continuity_state_id: string | null;
  images: Record<Finish, string>;
}

export interface PageDetail extends PageSummary {
  run_id: string;
  body: PageBody;
  bundle: PageBundle;
  dependencies: { kind: string; key: string; version_hash: string }[];
  attempts: PageAttempt[];
}

export interface Backend {
  kind: "TEST" | "COMFY_LOCAL" | "COMFY_REMOTE";
  provider_id: string;
  configured: boolean;
  reachable: boolean;
  ready: boolean;
  output: string;
  reason: string;
  endpoint?: string;
  missing_nodes?: string[];
  checkpoint_available?: boolean;
  identity_conditioning?: boolean;
  model?: Record<string, string>;
  model_metadata_missing?: string[];
  workflow?: { id: string; version: string; sha256: string };
}

export interface CharacterOverview {
  character: {
    id: string;
    display_name: string;
    origin: string;
    project_key: string | null;
    source_label: string;
    summary: string;
    design_documents: string[];
  };
  primary_visual: Observation | null;
  readiness: CorpusReadiness;
  counts: {
    total: number;
    by_status: Record<string, number>;
    by_authority: Record<string, number>;
    by_source: Record<string, number>;
    high_authority_confirmed: number;
  };
  anchors: Observation[];
  stylization: Observation[];
  invariants: { facet: string; statement: string; supported_by: number; distinct_sources: number; state: string }[];
  forbidden: string[];
  grounding_rule: string;
}

export interface ObservationList {
  total: number;
  observations: Observation[];
  counts?: CharacterOverview["counts"];
}

/* -- vocabulary ---------------------------------------------------------------- */
export const PAGE_STATE_TONE: Record<PageState, string> = {
  WAITING: "muted",
  BLOCKED: "err",
  READY: "info",
  IN_REVIEW: "accent",
  APPROVED: "ok",
  STALE: "warn",
};
export const PAGE_STATE_LABEL: Record<PageState, string> = {
  WAITING: "Waiting",
  BLOCKED: "Blocked",
  READY: "Ready",
  IN_REVIEW: "In review",
  APPROVED: "Approved",
  STALE: "Stale",
};
export const AUTHORITY_LABEL: Record<string, string> = {
  PRIMARY_SOURCE: "Primary source",
  CREATOR_PRIMARY: "Creator grounding",
  OFFICIAL: "Official",
  PROJECT_CREATED: "Project-created",
  SUPPLEMENTAL: "Supplemental",
  UNSORTED: "Unsorted",
};
export const AUTHORITY_ORDER = ["CREATOR_PRIMARY", "PRIMARY_SOURCE", "OFFICIAL", "PROJECT_CREATED", "SUPPLEMENTAL", "UNSORTED"];
export const FACETS = ["FACE", "HAIR", "BODY", "WARDROBE", "EXPRESSION", "POSE", "ACCESSORY", "SCALE"] as const;
export const ANGLES = ["FRONT", "THREE_QUARTER_LEFT", "THREE_QUARTER_RIGHT", "PROFILE", "BACK", "LOOKING_UP", "LOOKING_DOWN"] as const;
export const READINESS_TONE: Record<string, string> = { READY: "ok", PARTIAL: "warn", MISSING: "err" };

/** The decision that approves a page in this kind of run. */
export function approvalDecision(purpose: RunView["purpose"]): "TECHNICAL_PASS" | "CREATIVE_APPROVE" {
  return purpose === "PRODUCTION" ? "CREATIVE_APPROVE" : "TECHNICAL_PASS";
}

/** Why a page cannot be drawn yet, in words. */
export function pageBlocker(page: PageSummary, pages: PageSummary[]): string | null {
  if (page.state === "BLOCKED") {
    const missing = page.reasons.filter((r) => r.kind === "MISSING_REQUIRED_REFERENCE");
    return missing.length
      ? `Missing required references: ${missing.map((r) => r.detail ?? r.key).join("; ")}`
      : "Blocked.";
  }
  if (page.state === "WAITING") {
    const before = pages.find((p) => p.sequence === page.sequence - 1);
    return before
      ? `Waiting for page ${before.sequence}${before.integrated_page ? ` (p. ${before.integrated_page})` : ""} to be approved.`
      : "Waiting for the page before it to be approved.";
  }
  return null;
}

export const PENDING_ATTEMPT = new Set(["QUEUED", "RENDERING"]);

export function vaultImage(path: string): string {
  return `/vault-api${path.startsWith("/") ? path : `/${path}`}`;
}

export function shortHash(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 10) : "";
}

/* -- server-side reads ------------------------------------------------------------ */
async function read<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch (cause) {
    throw new ApiUnreachableError(
      `Cannot reach the Continuum API at ${API_BASE}. Start it with: uv run continuum-api`,
      { cause },
    );
  }
  if (response.status === 404) throw new VaultNotFound(path);
  if (!response.ok) throw new Error(`GET ${path} failed: ${response.status}`);
  return (await response.json()) as T;
}

const enc = encodeURIComponent;

export const manga = {
  backends: () => read<{ backends: Backend[] }>("/production/backends").then((r) => r.backends),
  runs: (project: string) => read<RunListItem[]>(`/projects/${enc(project)}/production-runs`),
  profiles: (project: string) => read<Profile[]>(`/projects/${enc(project)}/production-profiles`),
  run: (id: string) => read<RunView>(`/production/runs/${enc(id)}`),
  page: (id: string) => read<PageDetail>(`/production/pages/${enc(id)}`),
  overview: (characterId: string) => read<CharacterOverview>(`/library/characters/${enc(characterId)}/overview`),
  observations: (characterId: string, query: Record<string, string | undefined>) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) if (value) search.set(key, value);
    const text = search.toString();
    return read<ObservationList>(`/library/characters/${enc(characterId)}/observations${text ? `?${text}` : ""}`);
  },
};
