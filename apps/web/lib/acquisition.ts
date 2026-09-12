/**
 * Presentation vocabulary for Library Acquisition.
 *
 * The API speaks the engine's language (MAIN_WORK, PARTIAL, GUIDEBOOK). The
 * screens speak the user's. Keeping the mapping in one place means a label
 * change - or a translation - is one edit, and no screen invents its own
 * wording. Unknown values fall through to a readable form of themselves, so
 * a new relation added by the engine still renders sensibly.
 */

export type Tone = "ok" | "warn" | "err" | "muted" | "accent";

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
