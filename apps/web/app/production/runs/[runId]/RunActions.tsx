"use client";

import { useState } from "react";
import type { Reason, RunView } from "@/lib/manga";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../library/_vault/useAction";

interface Refreshed {
  changes: { sequence: number; page_key: string; reasons: Reason[] }[];
}

/** Refresh sources (selective invalidation) and, for an open sample, SAMPLE PASS / FAIL. */
export function RunActions({ run }: { run: RunView }) {
  const { busy, error, done, run: act } = useAction();
  const [notes, setNotes] = useState("");
  const [changes, setChanges] = useState<Refreshed["changes"] | null>(null);
  const sampleOpen = run.purpose === "NON_CANON_SAMPLE" && run.status === "OPEN";

  const refresh = async () => {
    const result = await act(() => vaultFetch<Refreshed>(`production/runs/${run.id}/refresh`, { method: "POST" }));
    if (result) setChanges(result.changes);
  };
  const decide = (passed: boolean) =>
    act(
      () => vaultFetch(`production/runs/${run.id}/sample-decision`, { json: { passed, notes } }),
      passed ? "SAMPLE PASS recorded: the profile is promoted (the images stay non-canon)." : "SAMPLE FAIL recorded.",
    );

  return (
    <div className="stack">
      <div className="surface panel stack">
        <div className="spread">
          <div className="stack" style={{ gap: 2 }}>
            <strong>Refresh sources</strong>
            <span className="hint">
              Re-reads the committed scripts, character references and profile. Only pages built from something that
              changed become stale; approved art is never replaced.
            </span>
          </div>
          <button className="button small" type="button" disabled={busy} onClick={refresh}>
            Refresh sources
          </button>
        </div>
        {changes ? (
          changes.length ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {changes.map((c) => (
                <li key={c.page_key}>
                  Page {c.sequence}: {c.reasons.map((r) => `${r.kind.toLowerCase().replaceAll("_", " ")} ${r.key ?? ""}`).join(", ")}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint" style={{ margin: 0 }}>
              Nothing changed: no page is stale.
            </p>
          )
        ) : null}
      </div>

      {run.purpose === "NON_CANON_SAMPLE" ? (
        <div className="surface panel stack">
          <strong>Sample decision</strong>
          {sampleOpen ? (
            <>
              <p className="hint" style={{ margin: 0 }}>
                SAMPLE PASS promotes this run&apos;s production profile to a frozen version canonical production can
                start from. It never promotes the images: they stay non-canon. A sample drawn only by the test renderer
                cannot pass.
              </p>
              <div className="field">
                <label>
                  Decision notes
                  <textarea value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: "100%", minHeight: 60 }} />
                </label>
              </div>
              <div className="row">
                <button className="button small primary" type="button" disabled={busy} onClick={() => decide(true)}>
                  Sample pass
                </button>
                <button className="button small ghost danger" type="button" disabled={busy} onClick={() => decide(false)}>
                  Sample fail
                </button>
              </div>
            </>
          ) : (
            <p className="hint" style={{ margin: 0 }}>
              Decided: {run.status.replace("_", " ").toLowerCase()}
              {run.decision_notes ? ` - ${run.decision_notes}` : ""}
            </p>
          )}
        </div>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}
