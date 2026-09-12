"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Re-reads the server-rendered data on an interval.
 *
 * The engine writes its documents from the outside - a scan, a discovery, a
 * scheduled pass - so a screen left open goes stale without anything on the
 * page changing. This asks the server for fresh output; it never runs the
 * engine itself, so it costs a file read and nothing more.
 */
export function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();

  useEffect(() => {
    const id = window.setInterval(() => {
      // Pausing while the tab is hidden keeps a forgotten tab from polling
      // all night for a screen nobody is looking at.
      if (document.visibilityState === "visible") router.refresh();
    }, seconds * 1000);
    return () => window.clearInterval(id);
  }, [router, seconds]);

  return null;
}
