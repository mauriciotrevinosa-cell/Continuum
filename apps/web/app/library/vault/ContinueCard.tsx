"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { type ContinueItem, progressLabel, unitHref } from "@/lib/catalog";
import { vaultFetch } from "@/lib/vault";

function progressWidth(item: ContinueItem): number {
  const p = item.progress;
  if (p.completed_at) return 100;
  if (p.medium === "READING" && p.page_count) {
    const first = item.unit?.first_page_index ?? 0;
    return Math.round((((p.page_index ?? first) - first + 1) / p.page_count) * 100);
  }
  if (p.position_ms && p.duration_ms) return Math.round((p.position_ms / p.duration_ms) * 100);
  return 4;
}

export function ContinueCardClient({ item }: { item: ContinueItem }) {
  const router = useRouter();
  const [busy, setBusy] = useState<"hide" | "reset" | null>(null);
  const [gone, setGone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const target = item.state === "next" && item.next ? item.next : item.unit;
  const href = target ? unitHref(target, item.state === "next" ? null : item.progress) : null;
  const isReading = item.progress.medium === "READING";
  const what =
    item.state === "next"
      ? isReading
        ? "Next chapter"
        : "Next episode"
      : item.state === "finished"
        ? "Finished"
        : isReading
          ? "Continue reading"
          : "Continue watching";

  async function act(action: "hide" | "reset") {
    if (busy) return;
    if (
      action === "reset" &&
      !window.confirm(
        `Forget all ${isReading ? "reading" : "watching"} progress for this title? It will start from the beginning next time.`,
      )
    ) {
      return;
    }
    setBusy(action);
    setError(null);
    try {
      await vaultFetch(`catalog/progress/${action}`, {
        method: "POST",
        json: { unit_key: item.progress.unit_key },
      });
      setGone(true);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(null);
    }
  }

  if (gone) return null;

  const body = (
    <>
      <span className="what">{what}</span>
      <span className="series">{target?.series_title ?? target?.source.file_name ?? "Unavailable"}</span>
      <span className="unit">
        {target ? target.label : "This file is not in the catalog right now."}
        {item.state === "resume" ? ` · ${progressLabel(item.progress, target?.first_page_index ?? 0) ?? ""}` : ""}
      </span>
      <span className="progress-line" aria-hidden>
        <i style={{ width: `${progressWidth(item)}%` }} />
      </span>
    </>
  );

  return (
    <div className="continue-card">
      {href ? (
        <Link className="continue-card-main" href={href}>
          {body}
        </Link>
      ) : (
        <div className="continue-card-main">{body}</div>
      )}
      <div className="continue-actions" aria-label="Continue options">
        <button type="button" onClick={() => void act("hide")} disabled={busy !== null}>
          {busy === "hide" ? "Hiding…" : "Hide"}
        </button>
        <button className="reset" type="button" onClick={() => void act("reset")} disabled={busy !== null}>
          {busy === "reset" ? "Resetting…" : isReading ? "Haven’t read" : "Haven’t watched"}
        </button>
      </div>
      {error ? <span className="continue-error">{error}</span> : null}
    </div>
  );
}
