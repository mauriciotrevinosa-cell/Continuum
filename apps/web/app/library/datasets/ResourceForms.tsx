"use client";

import { useState } from "react";
import { type ExternalResource, vaultFetch, words } from "@/lib/vault";
import { Feedback, useAction } from "../_vault/useAction";

/** Import a registry JSON file chosen by the person. Metadata only; validated by the API. */
export function ImportRegistry() {
  const { busy, error, done, run } = useAction();
  const upload = async (file: File | undefined) => {
    if (!file) return;
    const text = await file.text();
    let document: unknown;
    try {
      document = JSON.parse(text);
    } catch {
      await run(async () => {
        throw new Error("That file is not JSON.");
      });
      return;
    }
    await run(
      () =>
        vaultFetch<{ summary: Record<string, string[]> }>("library/external-resources/import", {
          json: document,
        }),
      "Registry imported. Decisions you already made were kept.",
    );
  };
  return (
    <div className="stack" style={{ gap: 6 }}>
      <label className="button small">
        {busy ? "Importing…" : "Import registry JSON"}
        <input
          type="file"
          accept="application/json,.json"
          hidden
          disabled={busy}
          onChange={(e) => void upload(e.target.files?.[0])}
        />
      </label>
      <Feedback error={error} done={done} />
    </div>
  );
}

/** Record a person's decision: access, license acceptance, allowed uses, intake binding. */
export function ResourceDecision({
  resource,
  intakeRoots,
  uses,
  accessStates,
}: {
  resource: ExternalResource;
  intakeRoots: { key: string; collection: string }[];
  uses: string[];
  accessStates: string[];
}) {
  const { busy, error, done, run } = useAction();
  const [access, setAccess] = useState(resource.access_state);
  const [allowed, setAllowed] = useState<string[]>(resource.allowed_uses);
  const [root, setRoot] = useState(resource.intake_root_key ?? "");
  const [note, setNote] = useState("");
  const [notes, setNotes] = useState(resource.notes);

  const save = () =>
    run(
      () =>
        vaultFetch(`library/external-resources/${resource.key}/decision`, {
          json: {
            row_version: resource.row_version,
            access_state: access,
            allowed_uses: allowed,
            ...(root ? { intake_root_key: root } : { clear_intake_root: true }),
            notes,
          },
        }),
      "Decision saved.",
    );
  const accept = (value: boolean) =>
    run(
      () =>
        vaultFetch(`library/external-resources/${resource.key}/decision`, {
          json: { row_version: resource.row_version, accept_license: value, acceptance_note: note },
        }),
      value ? "License acceptance recorded." : "License acceptance withdrawn (training approval with it).",
    );

  return (
    <details>
      <summary className="hint" style={{ cursor: "pointer" }}>
        Decide
      </summary>
      <div className="stack" style={{ gap: 8, marginTop: 8 }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <select aria-label="Access" value={access} onChange={(e) => setAccess(e.target.value)}>
            {accessStates.map((state) => (
              <option key={state} value={state}>
                Access: {words(state)}
              </option>
            ))}
          </select>
          <select aria-label="Intake folder" value={root} onChange={(e) => setRoot(e.target.value)}>
            <option value="">Bytes: not bound</option>
            {intakeRoots.map((r) => (
              <option key={r.key} value={r.key}>
                Bytes: {r.collection} ({r.key})
              </option>
            ))}
          </select>
        </div>
        <div className="chips">
          {uses.map((use) => (
            <button
              key={use}
              type="button"
              className={`chip tiny ${allowed.includes(use) ? "accent" : "quiet"}`}
              style={{ cursor: "pointer" }}
              aria-pressed={allowed.includes(use)}
              title={resource.proposed_uses.includes(use) ? "proposed by the registry" : "not proposed by the registry"}
              onClick={() => setAllowed(allowed.includes(use) ? allowed.filter((u) => u !== use) : [...allowed, use])}
            >
              {words(use)}
              {resource.proposed_uses.includes(use) ? "" : " *"}
            </button>
          ))}
        </div>
        <input aria-label="Notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes" />
        <div className="row">
          <button className="button small" type="button" disabled={busy} onClick={save}>
            Save decision
          </button>
        </div>
        <div className="row" style={{ gap: 6 }}>
          <input
            aria-label="Which terms were accepted"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Which terms, version and where they were accepted"
            style={{ flex: 1, minWidth: 0 }}
          />
          {resource.license_accepted_at ? (
            <button className="button small ghost danger" type="button" disabled={busy} onClick={() => accept(false)}>
              Withdraw acceptance
            </button>
          ) : (
            <button className="button small" type="button" disabled={busy || !note.trim()} onClick={() => accept(true)}>
              Record license acceptance
            </button>
          )}
        </div>
        <p className="hint" style={{ margin: 0 }}>
          * not proposed by the registry. Training approval needs an accepted license and granted (or open) access.
        </p>
        <Feedback error={error} done={done} />
      </div>
    </details>
  );
}
