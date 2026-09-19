"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { StageView } from "@/lib/manga";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../../../../library/_vault/useAction";

/** Refresh the screen while any stage is rendering. */
export function ConstructionRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [active, router]);
  return active ? (
    <span className="row" style={{ gap: 8 }}>
      <span className="spin" aria-hidden />
      <span className="hint">Rendering - refreshing</span>
    </span>
  ) : null;
}

/**
 * Render a stage on the frozen stage before it, then freeze, reject or
 * regenerate what came back. Only what the stage's state allows is offered.
 */
export function StageActions({ pageId, panel, stage }: { pageId: string; panel: number; stage: StageView }) {
  const { busy, error, done, run } = useAction();
  const [seed, setSeed] = useState("");
  const [notes, setNotes] = useState("");
  const latest = stage.attempts.at(-1) ?? null;
  const reviewable = latest !== null && latest.state === "GENERATED" && stage.state === "IN_REVIEW";
  const body = () => ({ seed: seed ? Number(seed) : null, notes });

  const render = () =>
    run(
      () =>
        vaultFetch(`production/pages/${pageId}/construction/${panel}/${stage.stage}/attempts`, {
          json: body(),
        }),
      `${stage.stage.toLowerCase()} queued on the frozen ${stage.contract.upstream?.toLowerCase() ?? "contract"}.`,
    );
  const review = (decision: "FREEZE" | "REJECT" | "REGENERATE") =>
    run(
      () =>
        vaultFetch(`production/stage-attempts/${latest!.id}/review`, {
          json: { decision, notes, seed: decision === "REGENERATE" && seed ? Number(seed) : null },
        }),
      decision === "FREEZE"
        ? "Frozen. The next stage builds on it; everything after it that was built on something else is now stale."
        : decision === "REJECT"
          ? "Rejected."
          : "Rejected; a new attempt is queued on the current upstream.",
    );

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
        {reviewable ? (
          <>
            <button className="button small primary" type="button" disabled={busy} onClick={() => review("FREEZE")}>
              Freeze
            </button>
            <button className="button small" type="button" disabled={busy} onClick={() => review("REGENERATE")}>
              Regenerate
            </button>
            <button className="button small ghost danger" type="button" disabled={busy} onClick={() => review("REJECT")}>
              Reject
            </button>
          </>
        ) : null}
        {stage.can_render && !reviewable ? (
          <button className="button small" type="button" disabled={busy} onClick={render}>
            {busy ? "Queuing…" : stage.attempts.length ? "Render again" : "Render stage"}
          </button>
        ) : null}
      </div>
      {stage.can_render || reviewable ? (
        <details>
          <summary className="hint" style={{ cursor: "pointer" }}>
            Seed and notes
          </summary>
          <div className="row" style={{ gap: 6, marginTop: 6 }}>
            <input
              aria-label="Notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Direction for this stage"
              style={{ flex: 1, minWidth: 0 }}
            />
            <input
              aria-label="Seed"
              type="number"
              min={0}
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              placeholder="seed"
              style={{ width: 90 }}
            />
          </div>
        </details>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}

/** Compose the page from every panel's frozen last stage. */
export function ComposePage({ pageId, ready, blocked }: { pageId: string; ready: boolean; blocked: string[] }) {
  const { busy, error, done, run } = useAction();
  const compose = () =>
    run(
      () => vaultFetch(`production/pages/${pageId}/compose`, { json: { notes: "" } }),
      "Page composition queued. Review it on the page screen.",
    );
  return (
    <div className="stack" style={{ gap: 6 }}>
      <button className="button small primary" type="button" disabled={busy || !ready} onClick={compose}>
        {busy ? "Composing…" : "Compose page from frozen finishes"}
      </button>
      {!ready && blocked.length ? <p className="hint">Waiting for: {blocked.join("; ")}</p> : null}
      <Feedback error={error} done={done} />
    </div>
  );
}
