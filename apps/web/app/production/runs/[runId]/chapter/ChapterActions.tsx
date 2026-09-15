"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../../library/_vault/useAction";

/** Start a CHAPTER TECHNICAL PREVIEW from a run, or test-render every preview page. */
export function ChapterActions({
  runId,
  preview,
  pending,
}: {
  runId: string;
  preview: boolean;
  pending: number;
}) {
  const router = useRouter();
  const { busy, error, done, run } = useAction();
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => router.refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [pending, router]);

  const startPreview = async () => {
    const created = await run(() =>
      vaultFetch<{ id: string }>(`production/runs/${runId}/preview`, { method: "POST" }),
    );
    if (created) router.push(`/production/runs/${created.id}/chapter`);
  };
  const renderAll = () =>
    run(
      () => vaultFetch<{ queued: number }>(`production/runs/${runId}/preview-render`, { method: "POST" }),
      "Test renders queued for every page.",
    );

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row">
        {preview ? (
          <button className="button small primary" type="button" disabled={busy} onClick={renderAll}>
            {busy ? "Preparing bundles…" : "Test-render every page"}
          </button>
        ) : (
          <button className="button small" type="button" disabled={busy} onClick={startPreview}>
            {busy ? "Creating preview…" : "Create chapter technical preview"}
          </button>
        )}
        {pending ? (
          <span className="row" style={{ gap: 8 }}>
            <span className="spin" aria-hidden />
            <span className="hint">{pending} page(s) rendering - refreshing</span>
          </span>
        ) : null}
      </div>
      <Feedback error={error} done={done} />
    </div>
  );
}
