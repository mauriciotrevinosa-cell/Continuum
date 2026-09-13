"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  type AttemptDetail,
  type CharacterSummary,
  type RoughArtifact,
  readerHref,
  vaultFetch,
  words,
} from "@/lib/vault";
import { Select } from "../../../library/_vault/SpecForm";
import { Feedback, useAction } from "../../../library/_vault/useAction";
import { STATE_TONE } from "../../_parts/status";

const image = (id: string, kind = "OUTPUT") =>
  `/vault-api/production/attempts/${id}/image${kind === "OUTPUT" ? "" : `?kind=${kind}`}`;

const PENDING = new Set(["QUEUED", "RENDERING"]);

function Review({ detail, characters }: { detail: AttemptDetail; characters: CharacterSummary[] }) {
  const { busy, error, done, run } = useAction();
  const [notes, setNotes] = useState("");
  const [seed, setSeed] = useState("");
  const [label, setLabel] = useState("");
  const [characterId, setCharacterId] = useState("");
  const decide = (decision: string) =>
    run(
      () =>
        vaultFetch(`production/attempts/${detail.id}/review`, {
          json: { decision, notes, seed: decision === "REGENERATE" && seed ? Number(seed) : null },
        }),
      decision === "REGENERATE" ? "A new attempt is queued." : `${words(decision)}d.`,
    );
  if (PENDING.has(detail.display_state) || detail.display_state === "BLOCKED" || detail.display_state === "FAILED") {
    return null;
  }
  return (
    <div className="stack">
      <div className="field">
        <label>
          Review notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: "100%", minHeight: 60 }} />
        </label>
      </div>
      <div className="row">
        {detail.state !== "APPROVED" ? (
          <button className="button small primary" type="button" disabled={busy} onClick={() => decide("APPROVE")}>
            Approve
          </button>
        ) : null}
        {detail.state !== "REJECTED" ? (
          <button className="button small" type="button" disabled={busy} onClick={() => decide("REJECT")}>
            Reject
          </button>
        ) : null}
        <button className="button small" type="button" disabled={busy} onClick={() => decide("REGENERATE")}>
          Regenerate
        </button>
        <div className="field compact" style={{ width: 130 }}>
          <input type="number" min={0} value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="new seed" aria-label="Seed for regeneration" />
        </div>
      </div>
      {detail.state === "APPROVED" ? (
        <div className="stack surface panel" style={{ background: "var(--surface-0)" }}>
          <strong>Keep as continuity</strong>
          <p className="hint">Makes this approved attempt a CONTINUITY reference for later pages.</p>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
            <div className="field compact">
              <label>
                Label
                <input value={label} onChange={(e) => setLabel(e.target.value)} style={{ width: "100%" }} />
              </label>
            </div>
            <Select
              label="Shows"
              value={characterId}
              onChange={setCharacterId}
              options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
              empty="-"
            />
            <button
              className="button small"
              type="button"
              disabled={busy}
              onClick={() =>
                run(
                  () =>
                    vaultFetch(`production/attempts/${detail.id}/continuity`, {
                      json: {
                        label,
                        characters: characterId ? [{ character_id: characterId, aspect: "FULL_BODY" }] : [],
                      },
                    }),
                  "Added to the vault as continuity.",
                )
              }
            >
              Add
            </button>
          </div>
        </div>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}

function Detail({ id, characters }: { id: string; characters: CharacterSummary[] }) {
  const [detail, setDetail] = useState<AttemptDetail | null>(null);
  const [kind, setKind] = useState("OUTPUT");
  const retry = useAction();

  useEffect(() => {
    let live = true;
    const load = () =>
      vaultFetch<AttemptDetail>(`production/attempts/${id}`)
        .then((d) => live && setDetail(d))
        .catch(() => live && setDetail(null));
    load();
    const timer = setInterval(() => {
      if (!detail || PENDING.has(detail.display_state)) load();
    }, 2000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [id, detail?.display_state]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!detail) return <p className="hint">Loading attempt…</p>;
  const intent = detail.recipe.intent;
  const kinds = detail.derivatives.map((d) => d.kind);
  const rendered = detail.derivatives.find((d) => d.kind === "OUTPUT")?.detail?.rendered_with as
    | { provider_id: string; workflow: string; version: string }
    | undefined;

  return (
    <div className="two-col">
      <div className="stack">
        <div className="spread">
          <h3 style={{ margin: 0 }}>
            Attempt {detail.attempt} <span className="muted">· {words(detail.mode)}</span>
          </h3>
          <span className={`chip ${STATE_TONE[detail.display_state] ?? "muted"}`}>{words(detail.display_state)}</span>
        </div>
        {detail.display_state === "BLOCKED" || detail.display_state === "FAILED" ? (
          <div className="banner err">
            <p>
              <strong>{detail.job?.blocked_reason ? words(detail.job.blocked_reason) : "Failed"}.</strong>{" "}
              {String(detail.job?.remediation?.message ?? detail.job?.error ?? "")}{" "}
              {String(detail.job?.remediation?.action ?? detail.job?.error_remediation ?? "")}
            </p>
            {detail.job ? (
              <button
                className="button small"
                type="button"
                disabled={retry.busy}
                onClick={() => retry.run(() => vaultFetch(`jobs/${detail.job!.id}/retry`, { json: {} }), "Queued again.")}
              >
                Retry
              </button>
            ) : null}
          </div>
        ) : null}
        <Feedback error={retry.error} done={retry.done} />
        {detail.content_hash ? (
          <>
            <div className="tabs" role="tablist" aria-label="Image">
              {["OUTPUT", "SOURCE_CROP", "MASK"].filter((k) => kinds.includes(k)).map((k) => (
                <button key={k} type="button" role="tab" aria-selected={kind === k} onClick={() => setKind(k)}>
                  {words(k)}
                </button>
              ))}
            </div>
            <div className="output-view">
              {/* eslint-disable-next-line @next/next/no-img-element -- generated bytes served by attempt id */}
              <img src={image(detail.id, kind)} alt={`Attempt ${detail.attempt} ${words(kind)}`} />
            </div>
          </>
        ) : (
          <div className="empty">
            <h3>{PENDING.has(detail.display_state) ? "Rendering in the worker…" : "No image"}</h3>
            <p>The worker renders attempts in the background; closing this page does not stop it.</p>
          </div>
        )}
        <Review detail={detail} characters={characters} />
      </div>

      <div className="stack">
        <section className="surface panel stack">
          <h3>Bundle</h3>
          {Object.entries(detail.bundle)
            .filter(([, entries]) => entries.length)
            .map(([role, entries]) => (
              <div className="bundle-role" key={role}>
                <span className="eyebrow" style={{ margin: 0 }}>
                  {words(role)}
                </span>
                {entries.map((entry) => {
                  const href = readerHref(entry.source);
                  return (
                    <div className="op-item" key={entry.position}>
                      <span>
                        {entry.label || entry.locator.split("#")[0].slice(0, 24)}
                        {entry.reference_origin ? <span className="muted"> · {words(entry.reference_origin)}</span> : null}
                        {!entry.reference_available ? <span className="muted"> · removed from catalog</span> : null}
                      </span>
                      <span className="row">
                        {entry.reference_id && entry.reference_available ? (
                          <Link className="button small ghost" href={`/library/references/${entry.reference_id}`}>
                            Reference
                          </Link>
                        ) : null}
                        {href ? (
                          <Link className="button small ghost" href={href} target="_blank">
                            Source ↗
                          </Link>
                        ) : null}
                      </span>
                    </div>
                  );
                })}
              </div>
            ))}
        </section>

        <section className="surface panel stack">
          <h3>Recipe</h3>
          {intent.characters?.length ? (
            <p className="soft" style={{ margin: 0 }}>
              {intent.characters
                .map(
                  (c) =>
                    `${c.name}${c.outfit_name ? ` in ${c.outfit_name}` : ""}${c.visual_mode_name ? ` [${c.visual_mode_name}]` : ""}${c.acting_direction ? ` - ${c.acting_direction}` : ""}`,
                )
                .join("; ")}
            </p>
          ) : null}
          {intent.visual_modes?.length ? (
            <p className="hint">
              Modes: {intent.visual_modes.map((m) => `${m.name}${m.scope ? ` (${words(m.scope)})` : ""}`).join(", ")}
            </p>
          ) : null}
          {intent.operations?.length ? (
            <div className="op-list">
              {intent.operations.map((op, index) => (
                <div className="op-item" key={index}>
                  <span>
                    <b>{words(op.kind)}</b>
                    {op.label ? ` · ${op.label}` : ""}
                  </span>
                  <span className="muted tabular">
                    {Math.round(op.region.width * 100)}×{Math.round(op.region.height * 100)}%
                  </span>
                </div>
              ))}
            </div>
          ) : null}
          <dl className="kv" style={{ padding: 0 }}>
            <dt>Seed</dt>
            <dd className="tabular">{String(detail.recipe.execution.seed ?? "")}</dd>
            <dt>Workflow</dt>
            <dd>{String(detail.recipe.execution.workflow ?? "")}</dd>
            {rendered ? (
              <>
                <dt>Rendered with</dt>
                <dd>
                  {rendered.provider_id} v{rendered.version}
                </dd>
              </>
            ) : null}
            <dt>Intent hash</dt>
            <dd>
              <code>{detail.recipe.intent_hash.slice(0, 16)}…</code>
            </dd>
            <dt>Execution hash</dt>
            <dd>
              <code>{detail.recipe.execution_hash.slice(0, 16)}…</code>
            </dd>
            {detail.parent_attempt_id ? (
              <>
                <dt>Regenerated from</dt>
                <dd>an earlier attempt</dd>
              </>
            ) : null}
          </dl>
        </section>

        {detail.reviews.length ? (
          <section className="surface panel stack">
            <h3>Reviews</h3>
            <ol className="chain">
              {detail.reviews.map((r, index) => (
                <li key={index}>
                  <b>{words(r.decision)}</b>
                  {r.notes ? ` - ${r.notes}` : ""}{" "}
                  <span className="muted">{r.decided_at ? new Date(r.decided_at).toLocaleString() : ""}</span>
                </li>
              ))}
            </ol>
          </section>
        ) : null}
      </div>
    </div>
  );
}

/** Every attempt at this page or panel, newest first; nothing is overwritten. */
export function AttemptHistory({
  artifact,
  characters,
}: {
  artifact: RoughArtifact;
  characters: CharacterSummary[];
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(artifact.attempts[0]?.id ?? null);
  const pending = artifact.attempts.some((a) => PENDING.has(a.display_state));

  useEffect(() => {
    if (!selected && artifact.attempts[0]) setSelected(artifact.attempts[0].id);
  }, [artifact.attempts, selected]);

  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => router.refresh(), 2500);
    return () => clearInterval(timer);
  }, [pending, router]);

  useEffect(() => {
    // A newly requested attempt becomes the one on screen.
    const newest = artifact.attempts[0]?.id;
    if (newest) setSelected(newest);
  }, [artifact.attempts.length]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!artifact.attempts.length) {
    return (
      <div className="empty">
        <h3>No attempts yet</h3>
        <p>Build the recipe below and request the first one.</p>
      </div>
    );
  }
  return (
    <div className="stack">
      <div className="attempt-strip" role="list">
        {artifact.attempts.map((attempt) => (
          <button
            key={attempt.id}
            type="button"
            role="listitem"
            className="attempt-card"
            data-selected={attempt.id === selected}
            onClick={() => setSelected(attempt.id)}
          >
            <div className="ref-thumb">
              {attempt.content_hash ? (
                // eslint-disable-next-line @next/next/no-img-element -- generated bytes served by attempt id
                <img src={image(attempt.id)} alt={`Attempt ${attempt.attempt}`} loading="lazy" style={{ background: "#fff" }} />
              ) : (
                <span className="muted">{words(attempt.display_state)}</span>
              )}
            </div>
            <span className="row" style={{ justifyContent: "space-between" }}>
              <b className="tabular">#{attempt.attempt}</b>
              <span className={`chip tiny ${STATE_TONE[attempt.display_state] ?? "muted"}`}>
                {words(attempt.display_state)}
              </span>
            </span>
          </button>
        ))}
      </div>
      {selected ? <Detail key={selected} id={selected} characters={characters} /> : null}
    </div>
  );
}
