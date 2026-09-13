/**
 * Which dropped files are worth sending to the Reference Inbox, and as what.
 *
 * Only a hint: the server reads the bytes and decides (a JPEG named .heic is a
 * JPEG, an installer is refused). The browser's MIME type is often empty for
 * HEIC on Windows, so extensions count too - and nothing is dropped silently:
 * whatever is skipped here is named back to the person.
 */

const IMAGE_EXTENSIONS = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp", "heic", "heif", "avif"]);
const VIDEO_EXTENSIONS = new Set(["mp4", "m4v", "mov", "webm", "mkv"]);

export type IntakeHint = "IMAGE" | "SCREENSHOT" | "VIDEO";

export function intakeHint(name: string, type: string, screenshots: boolean): IntakeHint | null {
  const extension = name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
  if (type.startsWith("video/") || VIDEO_EXTENSIONS.has(extension)) return "VIDEO";
  if (type.startsWith("image/") || IMAGE_EXTENSIONS.has(extension)) {
    return screenshots ? "SCREENSHOT" : "IMAGE";
  }
  return null;
}

export interface IntakeTally {
  taken: number;
  duplicates: string[];
  refused: string[];
  skipped: string[];
}

export function describeTally(tally: IntakeTally): string {
  const parts = [`${tally.taken} taken in`];
  if (tally.duplicates.length) {
    parts.push(`${tally.duplicates.length} already in the inbox or library (${tally.duplicates.join(", ")})`);
  }
  if (tally.refused.length) parts.push(`${tally.refused.length} refused - ${tally.refused.join("; ")}`);
  if (tally.skipped.length) {
    parts.push(`${tally.skipped.length} not images or clips, not sent (${tally.skipped.join(", ")})`);
  }
  return `${parts.join(". ")}.`;
}
