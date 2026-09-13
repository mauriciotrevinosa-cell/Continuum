/**
 * Presentation vocabulary for Library Acquisition.
 *
 * The API speaks the engine's language (MAIN_WORK, PARTIAL, GUIDEBOOK). The
 * screens speak the user's. Keeping the mapping in one place means a label
 * change - or a translation - is one edit, and no screen invents its own
 * wording. Unknown values fall through to a readable form of themselves, so
 * a new relation added by the engine still renders sensibly.
 */

export type Tone = "ok" | "warn" | "err" | "info" | "muted" | "accent";

/** How one work relates to the rest of its family. OFFICIAL != MAIN CANON. */
export const RELATION_LABELS: Record<string, string> = {
  MAIN_WORK: "Main work",
  SEQUEL: "Sequel",
  PREQUEL: "Prequel",
  OFFICIAL_SPINOFF: "Spin-off",
  PARALLEL_ADAPTATION: "Parallel adaptation",
  ALTERNATE_ADAPTATION: "Alternate adaptation",
  IF_STORY: "If story",
  CROSSOVER_OFFICIAL: "Crossover",
  ONE_SHOT: "One-shot",
  SPECIAL_CHAPTER: "Special chapter",
  OFFICIAL_ANTHOLOGY: "Anthology",
  OFFICIAL_DOUJIN: "Official doujin",
  GUIDEBOOK: "Guidebook",
  FANBOOK_OFFICIAL: "Fanbook",
  ARTBOOK: "Art book",
  VISUAL_REFERENCE: "Visual reference",
  COLORED_EDITION: "Colour edition",
  DELUXE_OR_ALTERNATE_EDITION: "Edition variant",
  PROMOTIONAL_OFFICIAL: "Promotional",
  OTHER_OFFICIAL: "Other official",
  FAN_WORK: "Fan work",
  UNKNOWN: "Unclassified",
};

/** Story relations first, supplements after: the order the queue works in. */
export const RELATION_ORDER: string[] = [
  "MAIN_WORK",
  "SEQUEL",
  "PREQUEL",
  "OFFICIAL_SPINOFF",
  "PARALLEL_ADAPTATION",
  "ALTERNATE_ADAPTATION",
  "IF_STORY",
  "CROSSOVER_OFFICIAL",
  "ONE_SHOT",
  "SPECIAL_CHAPTER",
  "GUIDEBOOK",
  "FANBOOK_OFFICIAL",
  "ARTBOOK",
  "VISUAL_REFERENCE",
  "COLORED_EDITION",
  "DELUXE_OR_ALTERNATE_EDITION",
  "OFFICIAL_ANTHOLOGY",
  "OFFICIAL_DOUJIN",
  "PROMOTIONAL_OFFICIAL",
  "OTHER_OFFICIAL",
  "UNKNOWN",
  "FAN_WORK",
];

export const CLASS_LABELS: Record<string, string> = {
  manga: "Manga",
  manhwa: "Manhwa",
  manhua: "Manhua",
  "light-novel": "Light novel",
  "web-novel": "Web novel",
  anime: "Anime",
  anthology: "Anthology",
  "official-doujin": "Official doujin",
  guidebook: "Guidebook",
  fanbook: "Fanbook",
  "art-book": "Art book",
  "colored-edition": "Colour edition",
  "visual-reference": "Visual reference",
  special: "Special",
  "other-official": "Other official",
  "fan-art": "Fan art",
  "fan-work": "Fan work",
};

export const COVERAGE_LABELS: Record<string, string> = {
  COMPLETE: "Complete",
  PARTIAL: "Partial",
  MISSING: "Missing",
  UNKNOWN: "Unverified",
  BLOCKED: "Blocked",
};

/**
 * The Library's states, in the words a person uses.
 *
 * The distinction that matters most: "Missing" is a claim of absence and is
 * only shown when a fresh scan found nothing that could be the work. Material
 * that is on disk but not matched is "Needs mapping"; a "missing" verdict from
 * an out-of-date scan is "Needs rescan".
 */
export const STATE_LABELS: Record<string, string> = {
  COMPLETE: "Complete",
  PARTIAL: "Partial",
  PRESENT: "In library",
  MISSING: "Missing",
  NEEDS_MAPPING: "Needs mapping",
  UNVERIFIED: "Unverified",
  STALE: "Needs rescan",
  UNCATALOGUED: "Uncatalogued",
  EMPTY: "Nothing yet",
};

export const STATE_HINTS: Record<string, string> = {
  COMPLETE: "Everything known to exist is in your Library.",
  PARTIAL: "You have part of it.",
  PRESENT: "In your Library. Nothing is known to compare against, so completeness is not verified.",
  MISSING: "A fresh scan found nothing local that could be this.",
  NEEDS_MAPPING: "Local files of this kind exist but are not matched to a work yet.",
  UNVERIFIED: "Not established yet.",
  STALE: "The folder changed after the last scan. Refresh to know.",
  UNCATALOGUED: "Files are here, but the catalogue has no work for them.",
  EMPTY: "No material and no catalogued works.",
};

const STATE_TONES: Record<string, Tone> = {
  COMPLETE: "ok",
  PARTIAL: "warn",
  PRESENT: "accent",
  MISSING: "err",
  NEEDS_MAPPING: "info",
  UNVERIFIED: "muted",
  STALE: "muted",
  UNCATALOGUED: "info",
  EMPTY: "muted",
};

export function stateLabel(value: string | null | undefined): string {
  return STATE_LABELS[value ?? ""] ?? humanise(value);
}

export function stateTone(value: string | null | undefined): Tone {
  return STATE_TONES[value ?? ""] ?? "muted";
}

export function stateHint(value: string | null | undefined): string {
  return STATE_HINTS[value ?? ""] ?? "";
}

/** "3 minutes ago", "yesterday", "12 Sep": how long ago, for humans. */
export function timeAgo(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "never";
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return value;
  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);
  if (seconds < -60) {
    return then.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  return then.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: then.getFullYear() === now.getFullYear() ? undefined : "numeric",
  });
}

/** "Season 2 · 1–10", "Specials · 1–2", "Episodes 1–28". */
export function seasonLabel(season: number | null): string {
  if (season === null) return "Episodes";
  if (season === 0) return "Specials";
  return `Season ${season}`;
}

/** [1, 2, 3, 5, 8, 9] -> "1–3, 5, 8–9": what is held, without implying the gaps. */
export function numberRanges(values: number[]): string {
  const sorted = [...new Set(values)].sort((x, y) => x - y);
  const parts: string[] = [];
  let start = sorted[0];
  let previous = sorted[0];
  for (const value of sorted.slice(1)) {
    if (value === previous + 1) {
      previous = value;
      continue;
    }
    parts.push(start === previous ? String(start) : `${start}–${previous}`);
    start = previous = value;
  }
  if (sorted.length) parts.push(start === previous ? String(start) : `${start}–${previous}`);
  return parts.join(", ");
}

export function dash(range: string): string {
  return range.replaceAll("-", "–");
}

export const CAPABILITY_LABELS: Record<string, string> = {
  DISCOVERY_ONLY: "Discovery",
  METADATA: "Metadata",
  UPDATE_TRACKING: "Update tracking",
  MANUAL_ACQUISITION: "Manual acquisition",
  AUTOMATIC_ACQUISITION: "Automatic acquisition",
};

export const ADAPTER_LABELS: Record<string, string> = {
  web: "Website",
  "local-folder": "Local folder",
  bibliographic: "Catalogue",
};

const COVERAGE_TONES: Record<string, Tone> = {
  COMPLETE: "ok",
  PARTIAL: "warn",
  MISSING: "err",
  UNKNOWN: "muted",
  BLOCKED: "muted",
};

const LAYOUT_TONES: Record<string, Tone> = {
  FOUND: "ok",
  LEGACY_MAPPING: "accent",
  CONTAINED: "ok",
  MISSING_CONTENT: "warn",
  MISSING_FOLDER: "err",
  REVIEW_REQUIRED: "warn",
  AMBIGUOUS: "warn",
  CONFLICT: "err",
};

export function humanise(value: string | null | undefined): string {
  if (!value) return "—";
  return value
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .replace(/^\w/, (c) => c.toUpperCase());
}

export function relationLabel(value: string | null | undefined): string {
  if (!value) return "Unclassified";
  return RELATION_LABELS[value] ?? humanise(value);
}

export function classLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return CLASS_LABELS[value] ?? humanise(value);
}

export function coverageLabel(value: string | null | undefined): string {
  if (!value) return "Unverified";
  return COVERAGE_LABELS[value] ?? humanise(value);
}

export function coverageTone(value: string | null | undefined): Tone {
  return COVERAGE_TONES[value ?? ""] ?? "muted";
}

export function layoutTone(value: string | null | undefined): Tone {
  return LAYOUT_TONES[value ?? ""] ?? "muted";
}

export function capabilityLabel(value: string): string {
  return CAPABILITY_LABELS[value] ?? humanise(value);
}

export function adapterLabel(value: string): string {
  return ADAPTER_LABELS[value] ?? humanise(value);
}

/** Fraction of a family that is fully in the library (0..1). */
export function completion(family: {
  works_total: number;
  complete: number;
  partial: number;
}): number {
  if (!family.works_total) return 0;
  // A partial work counts as half: it is real progress, but it is not done.
  return Math.min(1, (family.complete + family.partial * 0.5) / family.works_total);
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "—";
  // Decimal units, matching what the acquisition CLI prints: the same
  // library must not appear to be two different sizes in two places.
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value >= 100 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatWhen(value: string | null | undefined): string {
  if (!value) return "never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Chapters/volumes in one short phrase, or "" when there is nothing to say. */
export function coverageDetail(work: {
  chapters: number;
  chapter_min: number | null;
  chapter_max: number | null;
  gaps: string;
  missing_chapters: string;
  remote_latest_chapter: number | null;
  local_files: number;
}): string {
  const parts: string[] = [];
  if (work.chapters && work.chapter_min !== null && work.chapter_max !== null) {
    parts.push(`ch ${work.chapter_min}–${work.chapter_max} (${work.chapters})`);
  } else if (work.local_files) {
    parts.push(`${work.local_files} files`);
  }
  if (work.gaps) parts.push(`gaps ${work.gaps}`);
  if (work.missing_chapters) parts.push(`missing ${work.missing_chapters}`);
  else if (work.remote_latest_chapter) parts.push(`latest known ${work.remote_latest_chapter}`);
  return parts.join(" · ");
}

/** The last segment of a path, whichever separator it uses. */
export function basename(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? path;
}

/**
 * A Vault path as the user thinks of it: relative to their Vault root.
 *
 * The absolute path is true but not informative - every row would start with
 * the same forty characters. The root itself is stated once per screen,
 * under "where this lives".
 */
export function inVault(path: string, vaultRoot: string): string {
  if (!vaultRoot) return path;
  const normal = (s: string) => s.replaceAll("\\", "/").replace(/\/+$/, "");
  const root = normal(vaultRoot);
  const value = normal(path);
  if (value.toLowerCase().startsWith(`${root.toLowerCase()}/`)) {
    return value.slice(root.length + 1);
  }
  return path;
}

/** "1 work", "3 works": a count the user reads, not a count plus an "s". */
export function plural(count: number, noun: string, plural?: string): string {
  return `${count} ${count === 1 ? noun : (plural ?? `${noun}s`)}`;
}
