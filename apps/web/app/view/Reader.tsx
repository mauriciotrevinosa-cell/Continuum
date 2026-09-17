"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Region } from "@/lib/regions";
import { type CharacterSummary, type VisualMode, vaultFetch } from "@/lib/vault";
import { AddReference, type ProjectChoice } from "../library/_vault/AddReference";
import { RegionSelector } from "../library/_vault/RegionSelector";

/** "Ch0003" -> "Chapter 3"; any other folder name is shown as it is. */
function chapterName(label: string): string {
  if (!label) return "Pages";
  const last = label.split("/").pop() ?? label;
  const match = /^(?:ch(?:apter)?|c)[ _.-]?0*(\d+(?:\.\d+)?)$/i.exec(last);
  return match ? `Chapter ${match[1]}` : last;
}

interface Chapter {
  label: string;
  first: number;
  count: number;
}

/**
 * Pages of one image archive, one at a time.
 *
 * Pages are requested by position from this app's own /media route, which
 * forwards only the opaque id. Arrow keys turn pages; the next page is
 * fetched ahead so turning feels immediate.
 */
export function Reader({
  mediaId,
  total,
  chapters,
  title,
  sourceTitle,
  backHref,
  previousHref,
  nextHref,
  characters = [],
  modes = [],
  projects = [],
}: {
  mediaId: string;
  total: number;
  chapters: Chapter[];
  title: string;
  sourceTitle?: string;
  backHref: string;
  previousHref: string | null;
  nextHref: string | null;
  characters?: CharacterSummary[];
  modes?: VisualMode[];
  projects?: ProjectChoice[];
}) {
  const [page, setPage] = useState(0);
  const [picking, setPicking] = useState(false);
  const [region, setRegion] = useState<Region | null>(null);
  const [fit, setFit] = useState<"height" | "width">("height");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const hash = Number.parseInt(window.location.hash.replace("#p", ""), 10);
    if (Number.isFinite(hash) && hash >= 1 && hash <= total) {
      setPage(hash - 1);
      return;
    }
    // No page in the link: pick up where this archive was left.
    void vaultFetch<{ position: { page_index: number | null } | null }>("catalog/progress/position", {
      query: { media_id: mediaId },
    })
      .then(({ position }) => {
        const saved = position?.page_index;
        if (saved !== null && saved !== undefined && saved > 0 && saved < total) {
          setPage(saved);
          window.history.replaceState(null, "", `#p${saved + 1}`);
        }
      })
      .catch(() => undefined);
  }, [mediaId, total]);

  // Remember the page a moment after it settles (reading, not flicking through).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void vaultFetch("catalog/progress/reading", { json: { media_id: mediaId, page_index: page } }).catch(
        () => undefined,
      );
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [mediaId, page]);

  const go = useCallback(
    (to: number) => {
      const next = Math.max(0, Math.min(total - 1, to));
      setPage(next);
      setFailed(false);
      setRegion(null);
      window.history.replaceState(null, "", `#p${next + 1}`);
    },
    [total],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLSelectElement ||
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement
      ) {
        return;
      }
      if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
        event.preventDefault();
        go(page + 1);
      } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        go(page - 1);
      } else if (event.key === "Home") go(0);
      else if (event.key === "End") go(total - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, page, total]);

  useEffect(() => {
    if (page + 1 < total) {
      const ahead = new Image();
      ahead.src = `/media/${mediaId}/page/${page + 1}`;
    }
  }, [mediaId, page, total]);

  const chapter = useMemo(() => {
    let current: Chapter | null = null;
    for (const c of chapters) if (c.first <= page) current = c;
    return current;
  }, [chapters, page]);

  return (
    <div className="reader">
      <header className="viewer-bar">
        <Link href={backHref} className="crumb" style={{ margin: 0 }}>
          ← {title}
        </Link>
        <div className="viewer-controls">
          {chapters.length > 1 ? (
            <>
              <label className="sr-only" htmlFor="chapter">
                Chapter
              </label>
              <select
                id="chapter"
                className="button small"
                value={chapter?.first ?? 0}
                onChange={(event) => go(Number(event.target.value))}
              >
                {chapters.map((c) => (
                  <option key={c.first} value={c.first}>
                    {chapterName(c.label)} · {c.count}
                  </option>
                ))}
              </select>
            </>
          ) : null}
          <button
            className={`button small${picking ? " primary" : " ghost"}`}
            type="button"
            aria-pressed={picking}
            onClick={() => {
              setPicking(!picking);
              setRegion(null);
            }}
          >
            {picking ? "Done adding" : "Add reference"}
          </button>
          <button className="button small ghost" type="button" onClick={() => setFit(fit === "height" ? "width" : "height")}>
            Fit {fit === "height" ? "width" : "height"}
          </button>
          <span className="muted tabular" aria-live="polite">
            {page + 1} / {total}
          </span>
        </div>
      </header>

      <div className={`page-stage fit-${fit}`} style={picking ? { paddingRight: 420 } : undefined}>
        <button className="page-turn prev" type="button" onClick={() => go(page - 1)} disabled={page === 0} aria-label="Previous page">
          ‹
        </button>
        {failed ? (
          <div className="empty" role="alert">
            <h3>This page couldn&apos;t be shown</h3>
            <p>The image may be damaged or in a format the browser can&apos;t display.</p>
          </div>
        ) : picking ? (
          <RegionSelector
            key={page}
            src={`/media/${mediaId}/page/${page}`}
            alt={`Page ${page + 1} of ${total}`}
            selecting
            draft={region}
            onSelect={setRegion}
            onError={() => setFailed(true)}
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- pages are private local bytes, not optimisable assets
          <img
            key={page}
            src={`/media/${mediaId}/page/${page}`}
            alt={`Page ${page + 1} of ${total}`}
            onError={() => setFailed(true)}
            onClick={() => go(page + 1)}
          />
        )}
        <button className="page-turn next" type="button" onClick={() => go(page + 1)} disabled={page >= total - 1} aria-label="Next page">
          ›
        </button>
      </div>

      {picking ? (
        <AddReference
          mediaId={mediaId}
          page={page}
          region={region}
          onClearRegion={() => setRegion(null)}
          characters={characters}
          modes={modes}
          projects={projects}
          sourceTitle={sourceTitle}
        />
      ) : null}

      <footer className="viewer-foot">
        {previousHref ? (
          <Link className="button small ghost" href={previousHref}>
            ← Previous file
          </Link>
        ) : (
          <span />
        )}
        <span className="muted">← → to turn pages</span>
        {nextHref ? (
          <Link className="button small ghost" href={nextHref}>
            Next file →
          </Link>
        ) : (
          <span />
        )}
      </footer>
    </div>
  );
}
