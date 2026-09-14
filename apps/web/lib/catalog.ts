/**
 * The full-Vault catalog, as the studio sees it.
 *
 * Shapes mirror the dictionaries the API assembles in continuum_library
 * (vault_views, progress, members, coverage, collection_import). Server
 * components read through `catalog` (direct to the API); client components act
 * through `vaultFetch` and the allowlisted /vault-api passage. Everything is
 * addressed by ids and keys - no path ever travels to or from the browser,
 * except the display names coverage shows so a person can find a file.
 */

import { API_BASE, ApiUnreachableError } from "./api";

/* -- shapes ---------------------------------------------------------------- */
export type UnitKind = "MANGA_CHAPTER" | "ARCHIVE_PAGES" | "EPISODE" | "VIDEO" | "IMAGE" | "DOCUMENT";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface ProgressView {
  medium: "READING" | "WATCHING";
  page_index: number | null;
  page_count: number | null;
  position_ms: number | null;
  duration_ms: number | null;
  opened_at: string | null;
  completed_at: string | null;
  unit_key?: string;
  series_key?: string | null;
}

export interface OpenLink {
  kind: "reader" | "player" | "member" | "image" | "document" | "intake" | "none";
  media_id?: string;
  member_id?: string;
  page_index?: number;
}

export interface UnitView {
  id: string;
  unit_key: string;
  kind: UnitKind;
  label: string;
  material_class: string;
  collection: string;
  series_key: string | null;
  series_title: string | null;
  program_title: string | null;
  subseries: string | null;
  season: number | null;
  episode: number | null;
  episode_kind: string | null;
  chapter_number: string | null;
  volume: number | null;
  first_page_index: number | null;
  page_count: number | null;
  confidence: Confidence;
  evidence: string[];
  flags: string[];
  source: {
    entry_id: string;
    root_key: string;
    collection: string;
    file_name: string;
    status: string;
    detected_format: string;
    archive_view: string | null;
    byte_size: number;
    content_hash: string | null;
    member_id: string | null;
    member_name: string | null;
    member_bytes: number | null;
    member_cached: boolean;
    creator_handle: string | null;
    posted_at: string | null;
  };
  open: OpenLink;
  progress: ProgressView | null;
  previous_id?: string | null;
  next_id?: string | null;
  provenance?: Record<string, unknown>;
}

export interface SeriesSummary {
  series_key: string;
  title: string;
  materials: Record<string, number>;
  units: Record<string, number>;
  flagged: number;
  last_opened_at: string | null;
}

export interface ProgressRef {
  unit_key: string;
  progress: ProgressView | null;
  unit?: UnitView;
}

export interface SeriesDetail {
  series_key: string;
  title: string;
  reading: UnitView[];
  reading_groups: { label: string; units: UnitView[] }[];
  watching: { label: string; units: UnitView[] }[];
  other: UnitView[];
  progress: Record<"reading" | "watching", { last_opened: ProgressRef | null; last_completed: ProgressRef | null }>;
  uncertain: number;
  duplicate_copies_hidden: number;
}

export interface ContinueItem {
  state: "resume" | "next" | "finished";
  progress: ProgressView & { unit_key: string };
  unit: UnitView | null;
  next: UnitView | null;
}

export interface JobRef {
  id: string;
  job_type: string;
  status: string;
  units_total: number | null;
  units_done: number;
}

export interface RootStatus {
  root_key: string;
  collection: string;
  material: string;
  available: boolean;
  last_scan: {
    id: string;
    status: string;
    started_at: string;
    finished_at: string | null;
    counts: Record<string, unknown>;
    files: number | null;
    skipped: number | null;
  } | null;
  active_jobs: JobRef[];
}

export interface EntryRow {
  relative?: string;
  reason?: string | null;
  error?: string | null;
  attempts?: number;
  format?: string;
  bytes?: number;
}

export interface CoverageRoot {
  root_key: string;
  collection: string;
  available: boolean;
  last_completed_scan: { finished_at: string | null; counts: Record<string, unknown> } | null;
  discovered: {
    files: number;
    bytes: number;
    directories: number;
    skipped: number;
    skipped_by_reason: Record<string, number>;
    skipped_entries: { relative: string; reason: string }[];
  };
  entries: {
    total: number;
    bytes: number;
    by_status: Record<string, number>;
    by_kind: Record<string, number>;
    by_material: Record<string, number>;
    series: number;
  };
  hashes: Record<string, number>;
  archives: {
    total: number;
    by_view: Record<string, number>;
    members_indexed: number;
    image_members: number;
    video_members: number;
  };
  units: {
    by_kind: Record<string, number>;
    by_confidence: Record<string, number>;
    flagged: number;
    episodes_by_series: Record<string, number>;
    chapters_by_series: Record<string, number>;
    low_confidence: { label: string; flags: string[]; relative: string }[];
  };
  duplicates: { extra_copies: number; groups: number };
  not_searchable: Record<string, number>;
  unsupported: EntryRow[];
  failed: EntryRow[];
  missing: EntryRow[];
}

export interface Coverage {
  generated_at: string;
  totals: Record<string, number>;
  roots: CoverageRoot[];
  references: Record<string, Record<string, number> | number>;
  projects: { projects: number };
}

export interface MemberState {
  member_id: string;
  name: string;
  archive: string;
  byte_size: number;
  compressed_size: number;
  content_type: string;
  plays_in_browser: "yes" | "maybe";
  state: "not_prepared" | "preparing" | "ready" | "unavailable";
  detail: string;
  job_id: string | null;
  job_status: string | null;
  unit: {
    id: string;
    label: string;
    series_key: string | null;
    series_title: string | null;
    season: number | null;
    episode: number | null;
    confidence: Confidence;
    flags: string[];
  } | null;
}

export interface ImportReport {
  collection: string;
  root_key: string;
  generated_at: string;
  defaults: Record<string, string>;
  totals: Record<string, number>;
  formats: Record<string, number>;
  rejected: { file: string; reason: string | null }[];
  failed: { file: string; reason: string | null }[];
  duplicates: { file: string; duplicate_of: string | null }[];
  unknown_creator: string[];
  unknown_date: string[];
  extension_mismatches: { file: string; detail: string }[];
}

export interface SearchResults {
  query: string;
  units: { total: number; units: UnitView[] };
  references: {
    id: string;
    label: string;
    origin: string;
    reference_class: string;
    collection: string;
    creator_handle: string | null;
    rights_status: string;
    training_eligibility: string;
  }[];
  candidates: { id: string; display_name: string; status: string; intake_kind: string; collection: string }[];
  documents: { project_id: string; project_title: string; id: string; title: string; lifecycle: string }[];
  music: { id: string; project_key: string; track: string; artist: string }[];
}

/* -- reads (server components) ------------------------------------------------ */
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
  if (response.status === 404) throw new CatalogNotFound(path);
  if (!response.ok) throw new Error(`GET ${path} failed: ${response.status}`);
  return (await response.json()) as T;
}

export class CatalogNotFound extends Error {}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const catalog = {
  roots: () => read<RootStatus[]>("/catalog/roots"),
  series: (q?: string, material?: string) => read<SeriesSummary[]>(`/catalog/series${query({ q, material })}`),
  seriesDetail: (key: string) => read<SeriesDetail>(`/catalog/series/${encodeURIComponent(key)}`),
  units: (params: Record<string, string | number | undefined>) =>
    read<{ total: number; units: UnitView[] }>(`/catalog/units${query(params)}`),
  unit: (id: string) => read<UnitView>(`/catalog/units/${encodeURIComponent(id)}`),
  search: (q: string) => read<SearchResults>(`/catalog/search${query({ q })}`),
  coverage: () => read<Coverage>("/catalog/coverage"),
  continueItems: () => read<ContinueItem[]>("/catalog/progress/continue"),
  member: (id: string) => read<MemberState>(`/catalog/members/${encodeURIComponent(id)}`),
  importReport: (slug: string) => read<ImportReport>(`/catalog/collections/${encodeURIComponent(slug)}/import`),
};

/* -- helpers --------------------------------------------------------------------- */
export const SERIES_KEY = /^[a-z0-9][a-z0-9-]{0,119}$/;
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const COLLECTION_SLUG = /^[a-z0-9][a-z0-9-]{0,39}$/;

/** Where a unit opens in the studio, resuming where the person left it. */
export function unitHref(unit: UnitView, progress: ProgressView | null = unit.progress): string | null {
  const open = unit.open;
  if (open.kind === "reader" && open.media_id) {
    const page = progress?.page_index ?? open.page_index ?? 0;
    return `/view/${open.media_id}#p${page + 1}`;
  }
  if (open.kind === "member" && open.member_id) {
    const at = progress?.position_ms ? `#t${Math.floor(progress.position_ms / 1000)}` : "";
    return `/watch/${open.member_id}${at}`;
  }
  if ((open.kind === "player" || open.kind === "image" || open.kind === "document") && open.media_id) {
    const at = open.kind === "player" && progress?.position_ms ? `#t${Math.floor(progress.position_ms / 1000)}` : "";
    return `/view/${open.media_id}${at}`;
  }
  return null;
}

export function rootLabel(rootKey: string, collection = ""): string {
  if (rootKey === "source_vault") return "Source Vault";
  return collection || rootKey.replace(/^intake:/, "");
}

export function collectionSlug(rootKey: string): string | null {
  return rootKey.startsWith("intake:") ? rootKey.slice("intake:".length) : null;
}

export function confidenceTone(confidence: Confidence): "ok" | "warn" | "err" {
  return confidence === "HIGH" ? "ok" : confidence === "MEDIUM" ? "warn" : "err";
}

export function progressLabel(progress: ProgressView | null): string | null {
  if (!progress) return null;
  if (progress.completed_at) return progress.medium === "READING" ? "Read" : "Watched";
  if (progress.medium === "READING" && progress.page_index !== null) {
    return `Page ${progress.page_index + 1}`;
  }
  if (progress.position_ms !== null) {
    const total = Math.floor(progress.position_ms / 1000);
    const minutes = Math.floor(total / 60);
    const seconds = String(total % 60).padStart(2, "0");
    return `At ${minutes}:${seconds}`;
  }
  return "Opened";
}

export function kindLabel(kind: string): string {
  return (
    {
      MANGA_CHAPTER: "Chapter",
      ARCHIVE_PAGES: "Pages",
      EPISODE: "Episode",
      VIDEO: "Video",
      IMAGE: "Image",
      DOCUMENT: "Document",
    }[kind] ?? kind
  );
}
