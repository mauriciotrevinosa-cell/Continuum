"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { type ModelBuilderState, type ProductionModel } from "@/lib/manga";
import { vaultFetch, words } from "@/lib/vault";
import { Feedback, useAction } from "../../_vault/useAction";

function provenanceSummary(provenance: Record<string, unknown>): string | null {
  const backend = typeof provenance.backend === "string" ? provenance.backend : null;
  const model = provenance.model;
  const modelName = model && typeof model === "object" && "name" in model && typeof model.name === "string" ? model.name : null;
  return [backend, modelName].filter(Boolean).join(" · ") || null;
}

export function ModelBuilder({ model, initial }: { model: ProductionModel; initial: ModelBuilderState }) {
  const router = useRouter();
  const action = useAction();
  const [reviewer, setReviewer] = useState("");
  const build = (sheet_kind: "HEAD" | "FULL_BODY") =>
    action.run(async () => {
      await vaultFetch("library/character-model-sheet-attempts", {
        json: { model_id: model.id, sheet_kind, seed: Date.now() % 2147483647 },
      });
      router.refresh();
    }, "Model-sheet job queued.");
  const review = (id: string, decision: "APPROVE" | "REJECT" | "REGENERATE") =>
    action.run(async () => {
      await vaultFetch(`library/character-model-sheet-attempts/${id}/review`, {
        json: { decision, reviewer, notes: "" },
      });
      router.refresh();
    }, decision === "APPROVE" ? "Approved into a new draft Production Model version." : "Review saved.");
  return (
    <section className="block" aria-label="Character model builder">
      <div className="block-head"><h2>Character Model Builder <small>reference-grounded candidates</small></h2></div>
      <div className="surface panel stack">
        <p className="hint">HEAD: front · 3/4 · profile · back hair. FULL BODY: front · 3/4 · side · back. Every result remains project-created review material until you approve it.</p>
        {initial.readiness.ready ? (
          <div className="row">
            <button className="button small primary" disabled={action.busy} onClick={() => build("HEAD")}>Build HEAD candidate</button>
            <button className="button small primary" disabled={action.busy} onClick={() => build("FULL_BODY")}>Build FULL BODY candidate</button>
            <span className="chip ok">{initial.readiness.provider_id}</span>
          </div>
        ) : (
          <div className="banner"><strong>Artwork backend required.</strong> {initial.readiness.remediation.message} {initial.readiness.remediation.action}</div>
        )}
        <Feedback error={action.error} done={action.done} />
        {initial.attempts.some((attempt) => attempt.status === "GENERATED") ? (
          <div className="field compact"><label>Reviewer name<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Required for every decision" /></label></div>
        ) : null}
        {initial.attempts.map((attempt) => (
          <div className="op-item" key={attempt.id}>
            <span><b>{words(attempt.sheet_kind)}</b> · attempt {attempt.attempt} · {words(attempt.status)} · {attempt.reference_count} grounded references{provenanceSummary(attempt.provenance) ? <> · {provenanceSummary(attempt.provenance)}</> : null}</span>
            <span className="row">
              {attempt.image ? <a className="button small ghost" href={`/vault-api${attempt.image}`} target="_blank" rel="noreferrer">Inspect candidate</a> : <span className="muted">{attempt.job?.status ? `Job ${words(attempt.job.status)}` : "Waiting"}</span>}
              {attempt.status === "GENERATED" ? <>
                <button className="button small primary" disabled={action.busy || !reviewer.trim()} onClick={() => review(attempt.id, "APPROVE")}>Approve sheet</button>
                <button className="button small ghost" disabled={action.busy || !reviewer.trim()} onClick={() => review(attempt.id, "REGENERATE")}>Regenerate</button>
                <button className="button small ghost danger" disabled={action.busy || !reviewer.trim()} onClick={() => review(attempt.id, "REJECT")}>Reject</button>
              </> : null}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
