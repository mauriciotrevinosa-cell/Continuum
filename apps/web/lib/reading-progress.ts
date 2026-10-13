"use client";

/**
 * Where the reader left off, kept in the browser.
 *
 * This is deliberately per-browser state, not a Continuum record: it needs no
 * API, no migration and no running worker, so a place in a chapter survives
 * every restart of everything else. The trade is that it does not follow the
 * reader to another device. When reading progress needs to be shared or read
 * back by Continuum it belongs in Postgres behind the API - `media_progress`
 * is the shape, though its `root_key` check constrains it to catalog roots
 * today, so a project document would need its own table.
 *
 * Every accessor is guarded: storage throws in private windows and can come
 * back empty with site data cleared. A reader that cannot remember a place
 * must still render the novel.
 */

export interface ChapterPlace {
  /** 0..1 of the chapter scrolled. 1 means finished. */
  scroll: number;
  /** Set once the chapter has been read to the end. */
  completed?: boolean;
  updatedAt: number;
}

export interface SeriesProgress {
  /** The chapter the reader was last in. */
  lastDocumentId: string | null;
  places: Record<string, ChapterPlace>;
}

const EMPTY: SeriesProgress = { lastDocumentId: null, places: {} };

/** Finished at 96%: the last lines of a chapter sit above the viewport bottom. */
export const COMPLETE_AT = 0.96;

function key(projectId: string): string {
  return `continuum.reading.${projectId}`;
}

export function readProgress(projectId: string): SeriesProgress {
  try {
    const raw = window.localStorage.getItem(key(projectId));
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<SeriesProgress>;
    if (!parsed || typeof parsed !== "object" || !parsed.places) return EMPTY;
    return {
      lastDocumentId: parsed.lastDocumentId ?? null,
      places: parsed.places,
    };
  } catch {
    return EMPTY;
  }
}

function write(projectId: string, progress: SeriesProgress): void {
  try {
    window.localStorage.setItem(key(projectId), JSON.stringify(progress));
  } catch {
    // A reader with storage blocked still reads; it just never resumes.
  }
}

/** Remember which chapter is open, without claiming any of it has been read. */
export function recordOpen(projectId: string, documentId: string): void {
  const progress = readProgress(projectId);
  write(projectId, {
    lastDocumentId: documentId,
    places: {
      ...progress.places,
      [documentId]: progress.places[documentId] ?? { scroll: 0, updatedAt: Date.now() },
    },
  });
}

/**
 * Record how far through a chapter the reader is.
 *
 * Scroll only ever moves forward here, and `completed` is never taken back:
 * scrolling up to re-read a passage must not undo having finished a chapter.
 */
export function recordScroll(projectId: string, documentId: string, scroll: number): void {
  const progress = readProgress(projectId);
  const previous = progress.places[documentId];
  const next = Math.min(1, Math.max(0, scroll));
  const furthest = Math.max(previous?.scroll ?? 0, next);
  write(projectId, {
    lastDocumentId: documentId,
    places: {
      ...progress.places,
      [documentId]: {
        scroll: furthest,
        completed: previous?.completed || furthest >= COMPLETE_AT,
        updatedAt: Date.now(),
      },
    },
  });
}

/** A chapter the reader reached the end of, or opened the next one from. */
export function markCompleted(projectId: string, documentId: string): void {
  const progress = readProgress(projectId);
  const previous = progress.places[documentId];
  write(projectId, {
    lastDocumentId: progress.lastDocumentId ?? documentId,
    places: {
      ...progress.places,
      [documentId]: { scroll: 1, completed: true, updatedAt: previous?.updatedAt ?? Date.now() },
    },
  });
}

/**
 * Mark a whole run of chapters read, or put them back to unread.
 *
 * Reading that happened before anything recorded it is invisible, and there is
 * no way to infer it. This is how a reader tells the shelf where they already
 * are without paging through what they have finished.
 */
export function setChaptersRead(
  projectId: string,
  documentIds: string[],
  read: boolean,
): void {
  const progress = readProgress(projectId);
  const places = { ...progress.places };
  for (const id of documentIds) {
    if (read) places[id] = { scroll: 1, completed: true, updatedAt: Date.now() };
    else delete places[id];
  }
  const lastStillKnown =
    progress.lastDocumentId && places[progress.lastDocumentId]
      ? progress.lastDocumentId
      : read
        ? (documentIds[documentIds.length - 1] ?? null)
        : null;
  write(projectId, { lastDocumentId: lastStillKnown, places });
}

export function clearProgress(projectId: string): void {
  try {
    window.localStorage.removeItem(key(projectId));
  } catch {
    // Nothing to do: the caller only ever offers this, never depends on it.
  }
}

export interface ResumeTarget {
  documentId: string;
  /** True when the reader is mid-chapter rather than starting a fresh one. */
  midChapter: boolean;
  scroll: number;
}

/**
 * Where "Continue" should go, given the series in reading order.
 *
 * An unfinished chapter is resumed. A finished one hands over to the next
 * chapter that is not finished, so completing a volume moves the reader on
 * instead of parking them on the last page they saw.
 */
export function resumeTarget(
  progress: SeriesProgress,
  order: string[],
): ResumeTarget | null {
  const last = progress.lastDocumentId;
  if (last) {
    const place = progress.places[last];
    if (place && !place.completed) {
      return { documentId: last, midChapter: place.scroll > 0.02, scroll: place.scroll };
    }
    const index = order.indexOf(last);
    if (index >= 0) {
      const onwards = order.slice(index + 1).find((id) => !progress.places[id]?.completed);
      if (onwards) return { documentId: onwards, midChapter: false, scroll: 0 };
    }
  }
  const anyUnread = order.find((id) => !progress.places[id]?.completed);
  if (!anyUnread) return null;
  // Nothing read at all is not "continue": let the caller offer a fresh start.
  return Object.keys(progress.places).length
    ? { documentId: anyUnread, midChapter: false, scroll: 0 }
    : null;
}
