"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  FINISHES,
  type Finish,
  type PageAttempt,
  type PagePlan,
  type PageState,
  type RunView,
  approvalDecision,
  attemptPhase,
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

function since(iso: string | null | undefined, now: number): string {
  if (!iso) return "";
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ${seconds % 60}s ago`;
}

/**
 * What the latest attempt is doing now: queued, rendering, complete, failed -
 * with a spinner, how long, the last update, and the reason when it failed.
 * Refreshes the page while the attempt is active.
 */
export function JobStatus({ attempt, testBackend }: { attempt: PageAttempt | null; testBackend: boolean }) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());
  const { phase, active, failed } = attemptPhase(attempt);
  useEffect(() => {
    if (!active) return;
    const refresh = window.setInterval(() => router.refresh(), 2000);
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.clearInterval(refresh);
      window.clearInterval(tick);
    };
  }, [active, router]);
  if (!attempt) return null;
  const job = attempt.job;
  return (
    <div className="stack" style={{ gap: 6 }}>
      {testBackend ? <span className="test-banner">Workflow test - not artwork</span> : null}
      <div className="job-status" data-active={active} data-failed={failed} role="status" aria-live="polite">
        {active ? <span className="spin" aria-hidden /> : null}
        <div className="stack" style={{ gap: 2 }}>
          <strong>
            Attempt {attempt.attempt}: {phase}
          </strong>
          <span className="muted" style={{ fontSize: 12 }}>
            {job?.status ? `job ${job.status.toLowerCase()}` : "no job"}
            {attempt.created_at ? ` · requested ${since(attempt.created_at, now)}` : ""}
            {job?.started_at ? ` · started ${since(job.started_at, now)}` : ""}
            {job?.updated_at ? ` · last update ${since(job.updated_at, now)}` : ""}
            {attempt.generated_at ? ` · finished ${since(attempt.generated_at, now)}` : ""}
          </span>
          {failed ? (
            <span className="error-text" style={{ margin: 0 }}>
              {job?.error ?? job?.blocked_reason ?? "The render did not complete."}
              {job?.error_remediation ? ` ${job.error_remediation}` : ""}
              {job?.remediation && typeof job.remediation === "string" ? ` ${job.remediation}` : ""}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Generate, reject, regenerate or approve - only what the page's state and run allow. */
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
  const preview = purpose === "WORKFLOW_TEST";
  const approve = approvalDecision(purpose);
  const reviewable = latest !== null && latest.state === "GENERATED";
  const canGenerate = state !== "WAITING" && state !== "BLOCKED" && !attemptPhase(latest).active;

  const generate = () =>
    run(
      () =>
        vaultFetch(`production/pages/${pageId}/attempts`, {
          json: { seed: seed ? Number(seed) : null, notes },
        }),
      "Bundle prepared and attempt queued.",
    );
  const review = (decision: string) =>
    run(
      () =>
        vaultFetch(`production/page-attempts/${latest!.id}/review`, {
          json: { decision, notes, seed: decision === "REGENERATE" && seed ? Number(seed) : null },
        }),
      decision === "REGENERATE"
        ? "Rejected; a new attempt is queued."
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
            {approve ? (
              <button className="button small primary" type="button" disabled={busy} onClick={() => review(approve)}>
                {purpose === "PRODUCTION" ? "Approve (creative)" : "Approve for this sample"}
              </button>
            ) : null}
            <button className="button small" type="button" disabled={busy} onClick={() => review("REGENERATE")}>
              {busy ? "Working…" : "Regenerate"}
            </button>
            <button className="button small ghost danger" type="button" disabled={busy} onClick={() => review("REJECT")}>
              Reject
            </button>
          </>
        ) : null}
        {canGenerate && !reviewable ? (
          <button className="button small primary" type="button" disabled={busy} onClick={generate}>
            {busy ? "Preparing bundle…" : latest ? "Generate again" : "Generate"}
          </button>
        ) : null}
      </div>
      {preview ? (
        <p className="hint" style={{ margin: 0 }}>
          Chapter technical preview: test renders only. Pages here are never approved and never join continuity.
        </p>
      ) : purpose === "NON_CANON_SAMPLE" ? (
        <p className="hint" style={{ margin: 0 }}>
          Approving a sample page is a technical pass for this sample: it joins the run&apos;s continuity and opens the
          next page. It is never creative approval and never canon.
        </p>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}

/** Correct who appears on this page when the script-derived cast is wrong. Recorded. */
export function CastEditor({ pageId, plan, known }: { pageId: string; plan: PagePlan; known: string[] }) {
  const { busy, error, done, run } = useAction();
  const [present, setPresent] = useState<string[]>(plan.characters_present);
  const [primary, setPrimary] = useState(plan.primary_character ?? "");
  const derived = [...new Set([...plan.cast_source.script, ...plan.cast_source.dialogue])];
  const save = () =>
    run(
      () =>
        vaultFetch(`production/pages/${pageId}/cast`, {
          json: {
            add: present.filter((n) => !derived.includes(n)),
            remove: derived.filter((n) => !present.includes(n)),
            primary: primary || null,
          },
        }),
      "Cast saved.",
    );
  return (
    <details>
      <summary className="hint" style={{ cursor: "pointer" }}>
        Correct the cast
      </summary>
      <div className="stack" style={{ marginTop: 8, gap: 6 }}>
        <div className="chips">
          {known.map((name) => (
            <button
              key={name}
              type="button"
              className={`chip tiny ${present.includes(name) ? "accent" : "quiet"}`}
              style={{ cursor: "pointer" }}
              aria-pressed={present.includes(name)}
              onClick={() => setPresent(present.includes(name) ? present.filter((n) => n !== name) : [...present, name])}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="row">
          <select aria-label="Primary character" value={primary} onChange={(e) => setPrimary(e.target.value)}>
            <option value="">Primary: derived</option>
            {present.map((name) => (
              <option key={name} value={name}>
                Primary: {name}
              </option>
            ))}
          </select>
          <button className="button small" type="button" disabled={busy} onClick={save}>
            Save cast
          </button>
        </div>
        <Feedback error={error} done={done} />
      </div>
    </details>
  );
}
