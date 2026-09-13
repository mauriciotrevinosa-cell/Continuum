/**
 * The reference vault and rough production, as the studio sees them.
 *
 * Shapes mirror the dictionaries the API assembles in continuum_library.views
 * and continuum_production.views. Server components read through `vault`
 * (direct to the API); client components act through `vaultFetch`, which goes
 * through this app's allowlisted /vault-api passage.
 */

import { API_BASE, ApiUnreachableError } from "./api";
import type { Region } from "./regions";

/* -- vocabulary ------------------------------------------------------------ */
export const REFERENCE_CLASSES = ["CANON", "TECHNIQUE", "CONTINUITY", "MOOD"] as const;
export const USER_ORIGINS = ["SOURCE", "OFFICIAL_ART", "FAN_ART", "USER_CREATED"] as const;
export const REFERENCE_USES = [
  "IDENTITY",
  "OUTFIT",
  "EXPRESSION",
  "POSE",
  "ACCESSORY",
  "STYLE",
  "TECHNIQUE",
  "MOOD",
  "MONSTER_DESIGN",
  "SCENE_SOURCE",
  "SOURCE_PLATE",
  "CONTINUITY",
] as const;
export const ASPECTS = {
  IDENTITY: ["FACE", "HAIR", "FULL_BODY", "PROPORTIONS", "SCALE", "DISTINGUISHING_MARK", "POSTURE"],
  WARDROBE: ["OUTFIT", "ACCESSORY"],
  ACTING: ["EXPRESSION", "POSE", "GESTURE", "ACTION_POSE", "QUIET_ACTING", "COMEDIC_EXPRESSION"],
} as const;
export const TECHNIQUE_FACETS = [
  "PAGE_COMPOSITION",
  "PANEL_DENSITY",
  "PAGE_TURN",
  "ACTION_READABILITY",
  "FACIAL_ACTING",
  "DIALOGUE_FRAMING",
  "NEGATIVE_SPACE",
  "IMPACT_LANGUAGE",
  "SCREENTONE",
  "BACKGROUND_TREATMENT",
  "COMEDY",
  "HORROR",
  "ROMANCE",
  "ATMOSPHERE",
  "ESTABLISHING_SHOT",
  "EXPERIMENTAL_LAYOUT",
  "LIGHTING",
  "NIGHT_RENDERING",
  "CINEMATOGRAPHY",
  "MOTION_LANGUAGE",
] as const;
export const DESCRIPTOR_FACETS = [
  "ERA",
  "SEASON_WEATHER",
  "CONDITION",
  "EXPRESSION",
  "POSE",
  "SHOT_TYPE",
  "CAMERA_ANGLE",
  "SCENE_TYPE",
  "ACTION_INTENSITY",
  "DIALOGUE_DENSITY",
  "BACKGROUND_COMPLEXITY",
  "COMPOSITION",
  "PAGE_TURN_FUNCTION",
  "MOOD",
  "PANEL_GEOMETRY",
  "CHARACTER_COUNT",
  "LOCATION",
  "TAG",
] as const;
export const PANEL_SOURCE_ROLES = [
  "SOURCE_PLATE",
  "COMPOSITION",
  "ENVIRONMENT",
  "CONTINUITY",
  "COMPARISON",
  "MOOD",
] as const;
export const STANDINGS = ["USEFUL", "CANONICAL_FOR_PROJECT", "PREFERRED_FOR_CURRENT_LOOK"] as const;
export const SUBJECT_KINDS = ["CHARACTER", "MONSTER", "CREATURE"] as const;
export const OUTFIT_KINDS = ["SOURCE_DEFAULT", "SOURCE_ALTERNATE", "PROJECT", "OTHER"] as const;
export const MODE_CATEGORIES = [
  "BASE",
  "INTIMATE",
  "EXPRESSIVE_COMEDY",
  "COMEDIC_DEFORMATION",
  "HORROR_THREAT",
  "MEMORY_DREAM",
  "HEIGHTENED_PERCEPTION",
  "ACTION",
  "ATMOSPHERE",
  "MONSTER",
  "EXPERIMENTAL",
] as const;
export const MODE_SCOPES = ["EPISODE", "SCENE", "SEQUENCE", "PANEL", "EVENT"] as const;
export const MODE_TRIGGERS = ["DIRECTORIAL", "SCENE_TONE", "CHARACTER_CONTROLLED"] as const;
export const INTAKE_KINDS = ["URL", "IMAGE", "VIDEO", "SCREENSHOT"] as const;
export const BUNDLE_ROLES = ["CANON", "STYLE", "TECHNIQUE", "MOOD", "SOURCE_PLATE", "CONTINUITY"] as const;
export const ROUGH_MODES = ["NEW_GENERATION", "SOURCE_DERIVED_EDIT", "COMPOSITE", "LAYOUT_ONLY"] as const;
export const EDIT_OPERATIONS = [
  "PRESERVE",
  "REMOVE",
  "REPLACE",
  "INSERT",
  "CHANGE_EXPRESSION",
  "CHANGE_OUTFIT",
  "REMOVE_TEXT",
  "REPLACE_TEXT",
  "EXTEND_BACKGROUND",
  "REDRAW",
  "RESTYLE_LINES",
  "REFRAME",
  "ADAPT_PROPORTIONS",
] as const;

export type ReferenceClass = (typeof REFERENCE_CLASSES)[number];
export type BundleRole = (typeof BUNDLE_ROLES)[number];
export type RoughMode = (typeof ROUGH_MODES)[number];
export type EditOperationKind = (typeof EDIT_OPERATIONS)[number];

/** "FULL_BODY" -> "Full body". */
export function words(value: string | null | undefined): string {
  if (!value) return "";
  const text = value.toLowerCase().replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const ORIGIN_LABEL: Record<string, string> = {
  SOURCE: "Source",
  OFFICIAL_ART: "Official art",
  FAN_ART: "Fan art",
  USER_CREATED: "Your own",
  GENERATED: "Generated",
  PROJECT_APPROVED: "Project approved",
};

export const ORIGIN_TONE: Record<string, string> = {
  SOURCE: "info",
  OFFICIAL_ART: "ok",
  FAN_ART: "warn",
  USER_CREATED: "accent",
  GENERATED: "muted",
  PROJECT_APPROVED: "ok",
};

/* -- shapes ---------------------------------------------------------------- */
export interface SourcePosition {
  available: boolean;
  media_id?: string;
  page_index?: number | null;
  time_ms?: number | null;
  held_name?: string | null;
  reason?: string;
}

export interface ReferenceView {
  id: string;
  locator: string;
  unit_index: number | null;
  region: Region | null;
  reference_class: string;
  origin: string;
  label: string;
  notes: string;
  source_url: string | null;
  creator_handle: string | null;
  favorite: boolean;
  provenance: Record<string, unknown>;
  medium: string | null;
  asset_origin: string | null;
  row_version: number;
  created_at: string | null;
  removed: boolean;
  previewable: boolean;
  uses: string[];
  characters: {
    link_id: string;
    character_id: string;
    character_name: string;
    aspect: string;
    group: string;
    outfit_id: string | null;
    outfit_name: string | null;
    preferred: boolean;
    notes: string;
  }[];
  techniques: {
    link_id: string;
    facet: string;
    visual_mode_id: string | null;
    visual_mode_name: string | null;
    notes: string;
  }[];
  descriptors: {
    id: string;
    facet: string;
    value: string;
    origin: string;
    origin_label: string;
    confidence: number | null;
    analyzer_ref: string | null;
  }[];
  standings: {
    id: string;
    project_key: string;
    standing: string;
    character_id: string | null;
    notes: string;
  }[];
  panel_sources: {
    id: string;
    project_key: string;
    episode: string;
    chapter: number | null;
    page: number;
    panel: number | null;
    role: string;
    notes: string;
  }[];
  source?: SourcePosition;
}

export interface CharacterSummary {
  id: string;
  display_name: string;
  subject_kind: string;
  source_label: string;
  summary: string;
  scale_notes: string;
  distinguishing_marks: string;
  posture_notes: string;
  notes: string;
  row_version: number;
  updated_at: string | null;
}

export interface VaultCard {
  reference: ReferenceView;
  link_id: string;
  aspect: string;
  preferred: boolean;
  outfit_id: string | null;
  notes: string;
}

export interface Outfit {
  id: string;
  character_id: string;
  name: string;
  kind: string;
  project_key: string | null;
  era: string;
  season_weather: string;
  condition: string;
  notes: string;
  row_version: number;
  references: VaultCard[];
}

export interface VisualMode {
  id: string;
  name: string;
  category: string;
  description: string;
  notes: string;
  row_version: number;
}

export interface CharacterVault {
  character: CharacterSummary;
  identity: Record<string, VaultCard[]>;
  acting: Record<string, VaultCard[]>;
  wardrobe: { outfits: Outfit[]; unassigned: VaultCard[] };
  preferred: VaultCard[];
  sources: Record<string, number>;
  project_standing: Record<string, Record<string, string[]>>;
  scoped_visual_modes: {
    assignment_id: string;
    project_key: string;
    visual_mode: VisualMode;
    scope: string;
    trigger: string;
    episode: string | null;
    event_label: string | null;
  }[];
  reference_count: number;
}

export interface StyleVault {
  modes: (VisualMode & { references: { reference: ReferenceView; facet: string; notes: string }[] })[];
  by_facet: Record<string, { reference: ReferenceView; facet: string; notes: string }[]>;
  reference_count: number;
}

export interface ModeAssignment {
  id: string;
  project_key: string;
  visual_mode_id: string;
  scope: string;
  trigger: string;
  episode: string | null;
  scene: number | null;
  page_from: number | null;
  page_to: number | null;
  panel: number | null;
  event_label: string | null;
  character_id: string | null;
  notes: string;
}

export interface Candidate {
  id: string;
  batch_id: string | null;
  intake_kind: string;
  status: string;
  source_url: string | null;
  creator_handle: string | null;
  display_name: string;
  has_file: boolean;
  capture: Record<string, string | number>;
  origin: string;
  suggested_class: string | null;
  intended_uses: string[];
  tags: string[];
  notes: string;
  reference_id: string | null;
  row_version: number;
  created_at: string | null;
}

export interface InboxView {
  candidates: Candidate[];
  batches: { id: string; kind: string; label: string; created_at: string; counts: Record<string, number> }[];
}

export interface JobState {
  id: string;
  status: string;
  blocked_reason: string | null;
  remediation: Record<string, unknown> | null;
  error: string | null;
  error_remediation: string | null;
  attempts: number;
}

export interface AttemptSummary {
  id: string;
  artifact_id: string;
  attempt: number;
  state: string;
  display_state: string;
  mode: string;
  seed: number | null;
  content_hash: string | null;
  width: number | null;
  height: number | null;
  parent_attempt_id: string | null;
  created_at: string | null;
  generated_at: string | null;
  job: JobState | null;
}

export interface BundleMember {
  position: number;
  role: string;
  reference_id: string | null;
  locator: string;
  unit_index: number | null;
  region: Region | null;
  character_id: string | null;
  outfit_id: string | null;
  aspect: string | null;
  label: string;
  reference_available: boolean;
  reference_origin?: string;
  source: SourcePosition;
}

export interface AttemptDetail extends AttemptSummary {
  recipe: {
    id: string;
    mode: string;
    schema: number;
    template_package_version: string;
    intent_hash: string;
    execution_hash: string;
    intent: Record<string, unknown> & {
      operations?: { kind: string; region: Region; label: string }[];
      characters?: { character_id: string; name: string; outfit_name: string | null; acting_direction: string; visual_mode_name: string | null }[];
      visual_modes?: { name: string; source: string; scope?: string }[];
    };
    execution: Record<string, unknown>;
  };
  bundle: Record<string, BundleMember[]>;
  derivatives: { kind: string; content_hash: string; mime: string; width: number; height: number; detail: Record<string, unknown> }[];
  reviews: { decision: string; notes: string; decided_at: string | null }[];
}

export interface RoughArtifact {
  id: string;
  project_key: string;
  episode: string;
  chapter: number | null;
  page: number;
  panel: number | null;
  kind: string;
  title: string;
  brief: string;
  panel_script: { document: string | null; version: string | null };
  created_at: string | null;
  approved_attempt_id: string | null;
  attempts: AttemptSummary[];
  scene_sources?: { id: string; panel: number | null; role: string; notes: string; reference: ReferenceView }[];
  modes_in_effect?: { assignment_id: string; visual_mode_id: string; name: string; scope: string; trigger: string; character_id: string | null }[];
}

export interface Readiness {
  permitted: boolean;
  provider_id: string | null;
  is_fake: boolean;
  license_note: string | null;
  blocked_reason: string | null;
  remediation: Record<string, unknown> | null;
}

/* -- server-side reads ------------------------------------------------------ */
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

export class VaultNotFound extends Error {}

const q = (params: Record<string, string | number | undefined | null>) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const vault = {
  references: (filters: Record<string, string | undefined>) =>
    read<ReferenceView[]>(`/library/references${q({ limit: 200, ...filters })}`),
  reference: (id: string) => read<ReferenceView>(`/library/references/${encodeURIComponent(id)}`),
  characters: () => read<CharacterSummary[]>("/library/characters"),
  character: (id: string) => read<CharacterVault>(`/library/characters/${encodeURIComponent(id)}`),
  styles: () => read<StyleVault>("/library/visual-modes"),
  assignments: (project: string) =>
    read<ModeAssignment[]>(`/projects/${encodeURIComponent(project)}/visual-modes`),
  inbox: (status: string, kind?: string) =>
    read<InboxView>(`/library/inbox${q({ status, kind, limit: 300 })}`),
  artifacts: (project: string) =>
    read<RoughArtifact[]>(`/projects/${encodeURIComponent(project)}/rough-artifacts`),
  artifact: (id: string) =>
    read<RoughArtifact>(`/production/rough-artifacts/${encodeURIComponent(id)}`),
  attempt: (id: string) => read<AttemptDetail>(`/production/attempts/${encodeURIComponent(id)}`),
  readiness: () => read<Readiness>("/production/readiness"),
};

/* -- client-side actions --------------------------------------------------- */
export class VaultActionError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly remediation: string | null = null,
  ) {
    super(message);
  }
}

function explain(body: unknown, status: number): VaultActionError {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return new VaultActionError(detail, status);
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    const where = first?.loc ? first.loc.filter((p) => p !== "body").join(" › ") : "";
    return new VaultActionError(
      `${where ? `${where}: ` : ""}${first?.msg ?? "The request was not accepted."}`,
      status,
    );
  }
  if (detail && typeof detail === "object") {
    const d = detail as { message?: string; remediation?: string | null };
    return new VaultActionError(d.message ?? "The request was not accepted.", status, d.remediation ?? null);
  }
  return new VaultActionError(`The request failed (${status}).`, status);
}

/** Call the vault through the same-origin passage. JSON in, JSON out. */
export async function vaultFetch<T>(
  path: string,
  init: { method?: "GET" | "POST"; json?: unknown; body?: Blob | ArrayBuffer; query?: Record<string, string | number | undefined | null> } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;
  if (init.json !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(init.json);
  } else if (init.body !== undefined) {
    headers["content-type"] = "application/octet-stream";
    body = init.body;
  }
  const response = await fetch(`/vault-api/${path}${q(init.query ?? {})}`, {
    method: init.method ?? (body ? "POST" : "GET"),
    headers,
    body,
  });
  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  if (!response.ok) throw explain(parsed, response.status);
  return parsed as T;
}

export function referenceImage(id: string, crop = true): string {
  return `/vault-api/library/references/${id}/image${crop ? "" : "?crop=false"}`;
}

export function readerHref(source: SourcePosition | undefined): string | null {
  if (!source?.available || !source.media_id) return null;
  if (source.page_index !== null && source.page_index !== undefined) {
    return `/view/${source.media_id}#p${source.page_index + 1}`;
  }
  if (source.time_ms !== null && source.time_ms !== undefined) {
    return `/view/${source.media_id}#t${Math.floor(source.time_ms / 1000)}`;
  }
  return `/view/${source.media_id}`;
}

export function clock(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "";
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  const h = Math.floor(m / 60);
  return h ? `${h}:${String(m % 60).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}
