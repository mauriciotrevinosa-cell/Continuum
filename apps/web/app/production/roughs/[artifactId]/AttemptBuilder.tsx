"use client";

import { useEffect, useMemo, useState } from "react";
import type { Region } from "@/lib/regions";
import {
  BUNDLE_ROLES,
  type CharacterSummary,
  EDIT_OPERATIONS,
  REFERENCE_CLASSES,
  ROUGH_MODES,
  type ReferenceView,
  type RoughArtifact,
  type VisualMode,
  referenceImage,
  vaultFetch,
  words,
} from "@/lib/vault";
import { referenceTitle, Thumb } from "../../../library/_vault/parts";
import { RegionSelector } from "../../../library/_vault/RegionSelector";
import { Select, useOutfits } from "../../../library/_vault/SpecForm";
import { Feedback, useAction } from "../../../library/_vault/useAction";

interface Member {
  key: string;
  role: string;
  reference: ReferenceView;
  character_id: string;
  aspect: string;
}

interface Operation {
  key: string;
  kind: string;
  region: Region;
  label: string;
  character_id: string;
  text: string;
}

interface PlacementRow {
  key: string;
  region: Region;
  label: string;
  character_id: string;
}

interface Direction {
  character_id: string;
  outfit_id: string;
  acting_direction: string;
  visual_mode_id: string;
}

const MODE_HELP: Record<string, string> = {
  NEW_GENERATION: "Drawn from the bundle and the recipe, with no source plate.",
  SOURCE_DERIVED_EDIT: "Starts from one source plate: say what to keep, remove, replace or insert.",
  COMPOSITE: "Combines a plate or continuity element with other references and placements.",
  LAYOUT_ONLY: "Boxes for panels and characters - a cheap pass before any rendering.",
};

let counter = 0;
const nextKey = () => `k${(counter += 1)}`;

function blankFrame(width: number, height: number): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#f4f2ec"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function DirectionRow({
  direction,
  characters,
  modes,
  onChange,
  onRemove,
}: {
  direction: Direction;
  characters: CharacterSummary[];
  modes: VisualMode[];
  onChange: (d: Direction) => void;
  onRemove: () => void;
}) {
  const outfits = useOutfits(direction.character_id);
  return (
    <div className="op-item" style={{ gridTemplateColumns: "1fr auto" }}>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr 1.4fr" }}>
        <Select
          label="Character"
          value={direction.character_id}
          onChange={(v) => onChange({ ...direction, character_id: v, outfit_id: "" })}
          options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
          empty="Choose…"
        />
        <Select
          label="Outfit"
          value={direction.outfit_id}
          onChange={(v) => onChange({ ...direction, outfit_id: v })}
          options={outfits.map((o) => ({ value: o.id, label: o.name }))}
          empty="As referenced"
        />
        <Select
          label="Drawn in mode"
          value={direction.visual_mode_id}
          onChange={(v) => onChange({ ...direction, visual_mode_id: v })}
          options={modes.map((m) => ({ value: m.id, label: m.name }))}
          empty="Base"
        />
        <div className="field compact">
          <label>
            Acting
            <input
              value={direction.acting_direction}
              onChange={(e) => onChange({ ...direction, acting_direction: e.target.value })}
              placeholder="startled, half-turned"
              style={{ width: "100%" }}
            />
          </label>
        </div>
      </div>
      <button className="button small ghost danger" type="button" onClick={onRemove} aria-label="Remove character">
        ✕
      </button>
    </div>
  );
}

/**
 * Build one attempt's recipe: the mode, the reference bundle by role, who
 * appears and how, the edit intent on the source plate, and placements.
 */
export function AttemptBuilder({
  artifact,
  characters,
  modes,
}: {
  artifact: RoughArtifact;
  characters: CharacterSummary[];
  modes: VisualMode[];
}) {
  const { busy, error, done, run } = useAction();
  const [mode, setMode] = useState("SOURCE_DERIVED_EDIT");
  const [members, setMembers] = useState<Member[]>([]);
  const [directions, setDirections] = useState<Direction[]>([]);
  const [chosenModes, setChosenModes] = useState<string[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [placements, setPlacements] = useState<PlacementRow[]>([]);
  const [opKind, setOpKind] = useState("REMOVE");
  const [opLabel, setOpLabel] = useState("");
  const [opCharacter, setOpCharacter] = useState("");
  const [opText, setOpText] = useState("");
  const [placementCharacter, setPlacementCharacter] = useState("");
  const [placementLabel, setPlacementLabel] = useState("");
  const [brief, setBrief] = useState(artifact.brief);
  const [seed, setSeed] = useState("");
  const [search, setSearch] = useState({ reference_class: "", use: "", character_id: "" });
  const [found, setFound] = useState<ReferenceView[]>([]);
  const [addRole, setAddRole] = useState("CANON");
  const [strength, setStrength] = useState("");
  const isPanel = artifact.kind === "PANEL";
  const size = isPanel ? { width: 1000, height: 700 } : { width: 1000, height: 1414 };

  useEffect(() => {
    let live = true;
    vaultFetch<ReferenceView[]>("library/references", {
      query: { limit: 60, ...search },
    })
      .then((rows) => live && setFound(rows))
      .catch(() => live && setFound([]));
    return () => {
      live = false;
    };
  }, [search]);

  const plate = members.find((m) => m.role === "SOURCE_PLATE") ?? null;
  const usesPlacements = mode !== "SOURCE_DERIVED_EDIT";
  const usesOperations = mode === "SOURCE_DERIVED_EDIT" || mode === "COMPOSITE";

  const add = (reference: ReferenceView, role: string) => {
    if (role === "SOURCE_PLATE" && mode === "SOURCE_DERIVED_EDIT") {
      setMembers((m) => [...m.filter((x) => x.role !== "SOURCE_PLATE"), { key: nextKey(), role, reference, character_id: "", aspect: "" }]);
      setOperations([]);
      return;
    }
    const link = reference.characters[0];
    setMembers((m) => [
      ...m,
      {
        key: nextKey(),
        role,
        reference,
        character_id: link?.character_id ?? "",
        aspect: link?.aspect ?? "",
      },
    ]);
  };

  const suggestions = useMemo(
    () => artifact.scene_sources ?? [],
    [artifact.scene_sources],
  );

  const submit = () =>
    run(async () => {
      const body = {
        mode,
        brief,
        seed: seed ? Number(seed) : null,
        bundle: members.map((m) => ({
          role: m.role,
          reference_id: m.reference.id,
          character_id: m.character_id || null,
          aspect: m.aspect || null,
          label: referenceTitle(m.reference).slice(0, 120),
        })),
        characters: directions
          .filter((d) => d.character_id)
          .map((d) => ({
            character_id: d.character_id,
            outfit_id: d.outfit_id || null,
            acting_direction: d.acting_direction,
            visual_mode_id: d.visual_mode_id || null,
          })),
        visual_mode_ids: chosenModes,
        operations: usesOperations
          ? operations.map((o) => ({
              kind: o.kind,
              region: o.region,
              label: o.label,
              character_id: o.character_id || null,
              text: o.text,
            }))
          : [],
        placements: usesPlacements
          ? placements.map((p) => ({ region: p.region, label: p.label, character_id: p.character_id || null }))
          : [],
        execution: strength ? { strength: Number(strength) } : {},
      };
      await vaultFetch(`production/rough-artifacts/${artifact.id}/attempts`, { json: body });
    }, "Attempt queued. The worker renders it; this page updates by itself.");

  const characterName = (id: string) => characters.find((c) => c.id === id)?.display_name ?? "";

  return (
    <div className="stack">
      <section className="surface panel stack" aria-label="Mode">
        <h3>1 · Mode</h3>
        <div className="tabs" role="tablist">
          {ROUGH_MODES.map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)}>
              {words(m)}
            </button>
          ))}
        </div>
        <p className="hint">{MODE_HELP[mode]}</p>
      </section>

      <section className="surface panel stack" aria-label="Reference bundle">
        <h3>2 · Reference bundle</h3>
        {suggestions.length ? (
          <div className="stack">
            <span className="eyebrow" style={{ margin: 0 }}>
              Scene sources for this page
            </span>
            <div className="ref-grid small">
              {suggestions.map((s) => (
                <div className="ref-card" key={s.id}>
                  <Thumb reference={s.reference} />
                  <span className="ref-label">{words(s.role)}{s.panel ? ` · panel ${s.panel}` : ""}</span>
                  <button
                    className="button small"
                    type="button"
                    onClick={() => add(s.reference, s.role === "SOURCE_PLATE" ? "SOURCE_PLATE" : s.role === "CONTINUITY" ? "CONTINUITY" : s.role === "MOOD" ? "MOOD" : "CANON")}
                  >
                    Add
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {BUNDLE_ROLES.map((role) => {
          const inRole = members.filter((m) => m.role === role);
          if (!inRole.length) return null;
          return (
            <div className="bundle-role" key={role}>
              <span className="eyebrow" style={{ margin: 0 }}>
                {words(role)}
              </span>
              {inRole.map((m) => (
                <div className="op-item" key={m.key}>
                  <span className="row" style={{ flexWrap: "nowrap" }}>
                    {/* eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id */}
                    <img src={referenceImage(m.reference.id)} alt="" style={{ width: 44, height: 44, objectFit: "cover", borderRadius: 6 }} />
                    <span>
                      {referenceTitle(m.reference)}
                      <span className="muted"> · {words(m.reference.origin)}</span>
                    </span>
                  </span>
                  <button
                    className="button small ghost danger"
                    type="button"
                    aria-label="Remove from bundle"
                    onClick={() => {
                      setMembers((all) => all.filter((x) => x.key !== m.key));
                      if (m.role === "SOURCE_PLATE") setOperations([]);
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          );
        })}

        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
          <Select
            label="Find class"
            value={search.reference_class}
            onChange={(v) => setSearch({ ...search, reference_class: v })}
            options={REFERENCE_CLASSES}
            empty="Any"
          />
          <Select
            label="Find use"
            value={search.use}
            onChange={(v) => setSearch({ ...search, use: v })}
            options={["IDENTITY", "OUTFIT", "EXPRESSION", "POSE", "STYLE", "TECHNIQUE", "MOOD", "MONSTER_DESIGN", "SCENE_SOURCE", "SOURCE_PLATE", "CONTINUITY"]}
            empty="Any"
          />
          <Select
            label="Find character"
            value={search.character_id}
            onChange={(v) => setSearch({ ...search, character_id: v })}
            options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
            empty="Anyone"
          />
          <Select label="Add as" value={addRole} onChange={setAddRole} options={BUNDLE_ROLES} />
        </div>
        <div className="ref-grid small" style={{ maxHeight: 360, overflow: "auto" }}>
          {found.map((reference) => (
            <button
              key={reference.id}
              type="button"
              className="ref-card"
              style={{ textAlign: "left", cursor: "pointer", color: "inherit", font: "inherit" }}
              onClick={() => add(reference, addRole)}
              title={`Add as ${words(addRole)}`}
              disabled={!reference.previewable}
            >
              <Thumb reference={reference} />
              <span className="ref-label">{referenceTitle(reference)}</span>
              <span className="hint">{words(reference.origin)}</span>
            </button>
          ))}
        </div>
      </section>

      <section className="surface panel stack" aria-label="Characters">
        <h3>3 · Who appears</h3>
        {directions.map((d, index) => (
          <DirectionRow
            key={index}
            direction={d}
            characters={characters}
            modes={modes}
            onChange={(next) => setDirections((all) => all.map((x, i) => (i === index ? next : x)))}
            onRemove={() => setDirections((all) => all.filter((_, i) => i !== index))}
          />
        ))}
        <div className="row">
          <button
            className="button small"
            type="button"
            onClick={() => setDirections((all) => [...all, { character_id: "", outfit_id: "", acting_direction: "", visual_mode_id: "" }])}
          >
            Add a character
          </button>
        </div>
        {modes.length ? (
          <div className="field">
            <span className="label">Visual modes for the whole attempt</span>
            <div className="toggles" role="group" aria-label="Visual modes">
              {modes.map((m) => {
                const on = chosenModes.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    className="toggle"
                    aria-pressed={on}
                    onClick={() =>
                      setChosenModes(on ? chosenModes.filter((x) => x !== m.id) : [...chosenModes, m.id])
                    }
                  >
                    {m.name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
        {artifact.modes_in_effect?.length ? (
          <p className="hint">
            Already in effect here from the project:{" "}
            {artifact.modes_in_effect.map((m) => `${m.name} (${words(m.scope)})`).join(", ")}. They are
            recorded with the recipe automatically.
          </p>
        ) : null}
      </section>

      {usesOperations && plate ? (
        <section className="surface panel stack" aria-label="Edit intent">
          <h3>4 · What changes on the source plate</h3>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
            <Select label="Operation" value={opKind} onChange={setOpKind} options={EDIT_OPERATIONS} />
            <Select
              label="Who or what"
              value={opCharacter}
              onChange={setOpCharacter}
              options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
              empty="-"
            />
            <div className="field compact">
              <label>
                Label
                <input value={opLabel} onChange={(e) => setOpLabel(e.target.value)} placeholder="background figure" style={{ width: "100%" }} />
              </label>
            </div>
            {opKind === "REPLACE_TEXT" ? (
              <div className="field compact">
                <label>
                  New text
                  <input value={opText} onChange={(e) => setOpText(e.target.value)} style={{ width: "100%" }} />
                </label>
              </div>
            ) : (
              <span />
            )}
          </div>
          <p className="hint">Drag on the plate to mark the region for this operation.</p>
          <div className="picker-stage">
            <RegionSelector
              src={referenceImage(plate.reference.id, true)}
              alt="Source plate"
              selecting
              draft={null}
              boxes={operations.map((o) => ({
                key: o.key,
                region: o.region,
                kind: o.kind,
                label: `${words(o.kind)}${o.character_id ? ` · ${characterName(o.character_id)}` : o.label ? ` · ${o.label}` : ""}`,
              }))}
              onSelect={(region) => {
                if (!region) return;
                setOperations((all) => [
                  ...all,
                  { key: nextKey(), kind: opKind, region, label: opLabel, character_id: opCharacter, text: opText },
                ]);
              }}
            />
          </div>
          <div className="op-list">
            {operations.map((o) => (
              <div className="op-item" key={o.key}>
                <span>
                  <b>{words(o.kind)}</b>
                  {o.character_id ? ` · ${characterName(o.character_id)}` : ""}
                  {o.label ? ` · ${o.label}` : ""}
                  <span className="muted tabular">
                    {" "}
                    · {Math.round(o.region.width * 100)}×{Math.round(o.region.height * 100)}%
                  </span>
                </span>
                <button className="button small ghost danger" type="button" aria-label="Remove operation" onClick={() => setOperations((all) => all.filter((x) => x.key !== o.key))}>
                  ✕
                </button>
              </div>
            ))}
          </div>
          <div className="field compact" style={{ maxWidth: 240 }}>
            <label>
              Edit strength (for a future model; recorded)
              <input type="number" min={0} max={1} step={0.05} value={strength} onChange={(e) => setStrength(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
        </section>
      ) : usesOperations ? (
        <section className="surface panel">
          <p className="hint">Add a reference as a Source plate to mark what to keep, remove, replace or insert.</p>
        </section>
      ) : null}

      {usesPlacements ? (
        <section className="surface panel stack" aria-label="Placements">
          <h3>{usesOperations ? "5" : "4"} · Placements</h3>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <Select
              label="Character"
              value={placementCharacter}
              onChange={setPlacementCharacter}
              options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
              empty="-"
            />
            <div className="field compact">
              <label>
                Label
                <input value={placementLabel} onChange={(e) => setPlacementLabel(e.target.value)} placeholder="panel 1 / establishing" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <div className="picker-stage">
            <RegionSelector
              src={blankFrame(size.width, size.height)}
              alt="Frame"
              selecting
              draft={null}
              boxes={placements.map((p) => ({
                key: p.key,
                region: p.region,
                kind: "PLACEMENT",
                label: [p.label, characterName(p.character_id)].filter(Boolean).join(" · ") || "placement",
              }))}
              onSelect={(region) => {
                if (!region) return;
                setPlacements((all) => [
                  ...all,
                  { key: nextKey(), region, label: placementLabel, character_id: placementCharacter },
                ]);
              }}
            />
          </div>
          {placements.length ? (
            <button className="button small ghost" type="button" onClick={() => setPlacements([])}>
              Clear placements
            </button>
          ) : null}
        </section>
      ) : null}

      <section className="surface panel stack" aria-label="Request">
        <div className="field">
          <label>
            Brief
            <textarea value={brief} onChange={(e) => setBrief(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="row">
          <div className="field compact" style={{ width: 180 }}>
            <label>
              Seed (optional)
              <input type="number" min={0} value={seed} onChange={(e) => setSeed(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
          <button className="button primary" type="button" disabled={busy} onClick={submit}>
            Request attempt
          </button>
        </div>
        <Feedback error={error} done={done} />
      </section>
    </div>
  );
}
