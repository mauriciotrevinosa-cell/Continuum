"use client";

import Link from "next/link";
import { type ReactNode, useEffect } from "react";
import {
  COMPLETE_AT,
  markCompleted,
  readProgress,
  recordOpen,
  recordScroll,
} from "@/lib/reading-progress";

/** How often a scroll may write to storage. */
const THROTTLE_MS = 250;
/** Restore attempts while the chapter's markdown is still being laid out. */
const RESTORE_RETRIES_MS = [0, 120, 320, 700, 1400];

function scrollable(): number {
  return document.documentElement.scrollHeight - document.documentElement.clientHeight;
}

/**
 * Keeps the reader's place in this chapter, and puts them back in it.
 *
 * Renders nothing.
 *
 * Saving is on a plain timer rather than `requestAnimationFrame`: a tab that
 * is not painting - backgrounded, behind another window, mid-close - never
 * runs an animation frame, and that is exactly when a reader's last position
 * most needs to survive. The place is also flushed when the page is hidden,
 * because `pagehide` is the only event a closing tab reliably gets.
 *
 * A chapter is only ever marked read by *reaching the end of it*, never by
 * measuring zero scrollable height. That measurement is also what an unlaid-out
 * page returns, and a reader finding chapters they have not opened marked as
 * read would have no way to tell which ones were real.
 */
export function ChapterProgress({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId: string;
}) {
  useEffect(() => {
    recordOpen(projectId, documentId);

    const place = readProgress(projectId).places[documentId];
    const wants = place && !place.completed && place.scroll > 0.02 ? place.scroll : null;

    let restored = wants === null;
    let touched = false;
    let last = 0;
    let timer: number | undefined;

    // Markdown lays out after mount, so the height needed to restore a place
    // is not there yet. Retry briefly, and give up the moment the reader
    // scrolls themselves - yanking the page under them would be worse than
    // losing the place.
    const restores = RESTORE_RETRIES_MS.map((delay) =>
      window.setTimeout(() => {
        if (restored || touched || wants === null) return;
        const height = scrollable();
        if (height <= 0) return;
        window.scrollTo({ top: wants * height, behavior: "auto" });
        restored = true;
      }, delay),
    );

    const save = () => {
      timer = undefined;
      last = Date.now();
      const height = scrollable();
      if (height <= 0) return;
      const ratio = window.scrollY / height;
      recordScroll(projectId, documentId, ratio >= COMPLETE_AT ? 1 : ratio);
    };

    const onScroll = () => {
      // Once the reader drives, the restore stops competing with them.
      if (restored) touched = true;
      if (timer !== undefined) return;
      timer = window.setTimeout(save, Math.max(0, THROTTLE_MS - (Date.now() - last)));
    };

    const onHide = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      save();
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", onHide);
    document.addEventListener("visibilitychange", onHide);

    return () => {
      for (const id of restores) window.clearTimeout(id);
      if (timer !== undefined) window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", onHide);
      document.removeEventListener("visibilitychange", onHide);
    };
  }, [projectId, documentId]);

  return null;
}

/**
 * The pager's forward link, which also finishes the chapter being left.
 *
 * Moving on is the one unambiguous statement that a chapter is done, and it is
 * the only signal a chapter short enough never to scroll will ever produce.
 */
export function NextChapterLink({
  projectId,
  documentId,
  href,
  className,
  children,
}: {
  projectId: string;
  documentId: string;
  href: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link className={className} href={href} onClick={() => markCompleted(projectId, documentId)}>
      {children}
    </Link>
  );
}
