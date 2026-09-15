"use client";

import { useState } from "react";
import { ANGLES, FACETS, type Observation } from "@/lib/manga";
import { vaultFetch, words } from "@/lib/vault";
import { Feedback, useAction } from "../../_vault/useAction";

interface RefreshResult {
  curated_changes: number;
  source_pages_added: number;
  fan_art_added: number;
  layout_hints?: number;
  series: string[];
  note?: string;
}

/** Sync curated references and sweep the catalogued source manga for candidates. */
export function CorpusRefresh({ characterId, original }: { characterId: string; original: boolean }) {
  const { busy, error, done, run } = useAction();
  const [result, setResult] = useState<RefreshResult | null>(null);
  const refresh = async () => {
    const found = await run(() =>
      vaultFetch<RefreshResult>(`library/characters/${characterId}/corpus/refresh`, {
        json: { per_chapter: 2, max_source_pages: 600, analyze_limit: 24 },
      }),
    );
    if (found) setResult(found);
  };
  return (
    <div className="stack">
      <div className="row">
        <button className="button small" type="button" disabled={busy} onClick={refresh}>
          {busy ? "Searching the Vault…" : original ? "Sync creator references" : "Find observations in the Vault"}
        </button>
        <span className="hint">
          {original
            ? "An original character is grounded by the creator's references; franchise material is never swept."
            : "Sweeps the catalogued source manga for pages where the character likely appears. Found pages are candidates until you confirm them."}
        </span>
      </div>
      {result ? (
        <p className="hint" style={{ margin: 0 }}>
          {result.note ??
            `${result.source_pages_added} new source page candidates, ${result.fan_art_added} fan art candidates${
              result.series.length ? ` from ${result.series.length} catalogued series` : " - no catalogued source series found"
            }.`}
        </p>
      ) : null}
      <Feedback error={error} done={done} />
    </div>
  );
}

/** What a person says an observation shows. Reviews are never overwritten by refreshes. */
export function ObservationReview({ observation }: { observation: Observation }) {
  const { busy, error, done, run } = useAction();
  const [facets, setFacets] = useState<string[]>(observation.facets);
  const [angle, setAngle] = useState(observation.angle ?? "");
  const [expression, setExpression] = useState(observation.expression);
  const [pose, setPose] = useState(observation.pose);
  const [tags, setTags] = useState("");
  const send = (changes: Record<string, unknown>, message: string) =>
    run(() => vaultFetch(`library/character-observations/${observation.id}/review`, { json: changes }), message);
  const describe = () => ({
    facets,
    expression,
    pose,
    ...(angle ? { angle } : { clear_angle: true }),
  });
  const toggle = (facet: string) =>
    setFacets(facets.includes(facet) ? facets.filter((f) => f !== facet) : [...facets, facet]);

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="chips">
        {FACETS.map((facet) => (
          <button
            key={facet}
            type="button"
            className={`chip tiny ${facets.includes(facet) ? "accent" : "quiet"}`}
            style={{ cursor: "pointer" }}
            aria-pressed={facets.includes(facet)}
            onClick={() => toggle(facet)}
          >
            {words(facet)}
          </button>
        ))}
      </div>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
        <select aria-label="Angle" value={angle} onChange={(e) => setAngle(e.target.value)}>
          <option value="">Angle</option>
          {ANGLES.map((a) => (
            <option key={a} value={a}>
              {words(a)}
            </option>
          ))}
        </select>
        <input aria-label="Expression" placeholder="expression" value={expression} onChange={(e) => setExpression(e.target.value)} />
        <input aria-label="Pose" placeholder="pose" value={pose} onChange={(e) => setPose(e.target.value)} />
      </div>
      <div className="row" style={{ gap: 6 }}>
        <button
          className="button small primary"
          type="button"
          disabled={busy}
          onClick={() => send({ status: "CONFIRMED", ...describe() }, "Confirmed.")}
        >
          {observation.status === "CONFIRMED" ? "Save" : "Confirm"}
        </button>
        <button className="button small ghost danger" type="button" disabled={busy} onClick={() => send({ status: "REJECTED" }, "Rejected.")}>
          Not this character
        </button>
        <button
          className="button small ghost"
          type="button"
          disabled={busy}
          onClick={() => send({ atypical: !observation.atypical }, observation.atypical ? "No longer atypical." : "Marked atypical.")}
        >
          {observation.atypical ? "Typical" : "Atypical"}
        </button>
        {observation.status === "CONFIRMED" && observation.role === "GROUNDING" ? (
          <button
            className="button small ghost"
            type="button"
            disabled={busy}
            onClick={() => send({ anchor: !observation.anchor }, observation.anchor ? "Anchor removed." : "Now a production anchor.")}
          >
            {observation.anchor ? "Unanchor" : "Anchor"}
          </button>
        ) : null}
      </div>
      {observation.reference_id ? (
        <select
          aria-label="Visual origin"
          defaultValue={String(observation.evidence?.visual_origin ?? "")}
          onChange={(e) =>
            run(
              () =>
                vaultFetch(`library/character-observations/${observation.id}/visual-origin`, {
                  json: { visual_origin: e.target.value || null },
                }),
              "Visual origin recorded; where it was acquired is kept.",
            )
          }
        >
          <option value="">Visual origin: as acquired</option>
          {["PRIMARY_MANGA", "OFFICIAL_ANIME", "OFFICIAL_ART", "PROJECT_CREATED", "FAN_ART", "UNKNOWN"].map((v) => (
            <option key={v} value={v}>
              Visual origin: {words(v)}
            </option>
          ))}
        </select>
      ) : null}
      <div className="form-row" style={{ gridTemplateColumns: "1fr auto", gap: 6 }}>
        <input aria-label="Setting tags" placeholder="environment tags: forest, inn…" value={tags} onChange={(e) => setTags(e.target.value)} />
        <button
          className="button small ghost"
          type="button"
          disabled={busy || !tags.trim()}
          onClick={() =>
            run(
              () =>
                vaultFetch(`library/character-observations/${observation.id}/environment`, {
                  json: { tags: tags.split(",").map((t) => t.trim()).filter(Boolean) },
                }),
              "Added as an environment reference.",
            )
          }
        >
          Use as environment
        </button>
      </div>
      <Feedback error={error} done={done} />
    </div>
  );
}
