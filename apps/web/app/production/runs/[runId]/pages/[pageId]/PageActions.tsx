"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  FINISHES,
  type Finish,
  PENDING_ATTEMPT,
  type PageAttempt,
  type PageState,
  type RunView,
  approvalDecision,
  vaultImage,
} from "@/lib/manga";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../../../library/_vault/useAction";

/** Master, B&W and color of one attempt: the same composition, toggled in place. */
export function FinishViewer({ attempt }: { attempt: PageAttempt }) {
  const [finish, setFinish] = useState<Finish>("COLOR_FINISH");
  return (
    <div className="finish-view">
      <div className="finish-tabs" role="group" aria-label="Finish">
        {FINISHES.map((f) => (
          <button key={f.kind} type="button" aria-pressed={finish === f.kind} onClick={() => setFinish(f.kind)}>
            {f.label}
          </button>
        ))}
      </div>
      <div className="finish-frame">
        {/* eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id */}
        <img src={vaultImage(attempt.images[finish])} alt={`Attempt ${attempt.attempt} - ${finish}`} />
      </div>
    </div>
  );
}

/** Keeps the page current while an attempt is queued or rendering. */
export function AutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), 2000);
    return () => window.clearInterval(timer);
  }, [active, router]);
  return active ? <p className="hint">Rendering… this page refreshes by itself.</p> : null;
}

/** Generate, reject, regenerate or approve - only what the page's state allows. */
export function PageActions({
  pageId,
  state,
  purpose,
  latest,
}: {
  pageId: string;
  state: PageState;
  purpose: RunView["purpose"];
  latest: PageAttempt | null;
}) {
  const { busy, error, done, run } = useAction();
  const [seed, setSeed] = useState("");
  const [notes, setNotes] = useState("");
  const approve = approvalDecision(purpose);
  const reviewable = latest !== null && latest.state === "GENERATED";
  const canGenerate = state !== "WAITING" && state !== "BLOCKED" && !(latest && PENDING_ATTEMPT.has(latest.display_state));

  const generate = () =>
    run(
      () =>
        vaultFetch(`production/pages/${pageId}/attempts`, {
          json: { seed: seed ? Number(seed) : null, notes },
        }),
      "Attempt queued.",
    );
  const review = (decision: string) =>
    run(
      () =>
        vaultFetch(`production/page-attempts/${latest!.id}/review`, {
          json: { decision, notes, seed: decision === "REGENERATE" && seed ? Number(seed) : null },
        }),
      decision === "REGENERATE"
        ? "Rejected and regenerating."
        : decision === "REJECT"
          ? "Rejected. Generate again when ready."
          : "Approved. The page joins continuity and the next page opens.",
    );

  return (
    <div className="surface panel stack">
      <div className="form-row" style={{ gridTemplateColumns: "1fr 130px", alignItems: "end" }}>
        <div className="field compact">
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Direction or review notes" />
          </label>
        </div>
        <div className="field compact">
          <label>
            Seed
            <input type="number" min={0} value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="auto" />
          </label>
        </div>
      </div>
      <div className="row">
        {reviewable ? (
          <>
            <button className="button small primary" type="button" disabled={busy} onClick={() => review(approve)}>
              {purpose === "PRODUCTION" ? "Approve (creative)" : "Approve for this sample"}
            </button>
            <button className="button small" type="button" disabled={busy} onClick={() => review("REGENERATE")}>
              Regenerate
            </button>
            <button className="button small ghost danger" type="button" disabled={busy} onClick={() => review("REJECT")}>
              Reject
            </button>
          </>
        ) : null}
        {canGenerate && !reviewable ? (
          <button className="button small primary" type="button" disabled={busy} onClick={generate}>
            {latest ? "Generate again" : "Generate"}
          </button>
        ) : null}
      </div>
      {purpose === "NON_CANON_SAMPLE" ? (
        <p className="hint" style={{ margin: 0 }}>
          Approving a sample page is a technical pass for this sample: it joins the run&apos;s continuity and opens the
          next page. It is never creative approval and never canon.
        </p>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}
