"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Re-reads the server-rendered data when it is worth re-reading.
 *
 * The engine writes its documents from outside the browser - a scan, a
 * discovery pass - so a screen left open goes stale with nothing on the page
 * changing. But these documents change when the user runs something, not on
 * a clock, so polling every minute mostly asks a question whose answer has
 * not moved.
 *
 * Two triggers instead: coming back to the tab (the moment a scan you just
 * ran in a terminal would have finished), and a slow heartbeat for a screen
 * left visible on a second monitor. Both pause while the tab is hidden.
 */
export function AutoRefresh({ seconds = 300 }: { seconds?: number }) {
  const router = useRouter();

  useEffect(() => {
    const refreshIfVisible = () => {
      if (document.visibilityState === "visible") router.refresh();
    };
    const id = window.setInterval(refreshIfVisible, seconds * 1000);
    window.addEventListener("focus", refreshIfVisible);
    document.addEventListener("visibilitychange", refreshIfVisible);
    return () => {
      window.clearInterval(id);
      window.removeEventListener("focus", refreshIfVisible);
      document.removeEventListener("visibilitychange", refreshIfVisible);
    };
  }, [router, seconds]);

  return null;
}
