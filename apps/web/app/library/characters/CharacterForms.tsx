"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  type CharacterSummary,
  type CharacterRoster,
  OUTFIT_KINDS,
  SUBJECT_KINDS,
  vaultFetch,
} from "@/lib/vault";
import { Select, type ProjectChoice } from "../_vault/SpecForm";
import { Feedback, useAction } from "../_vault/useAction";

export function CreateCharacter({ roster, projects }: { roster: CharacterRoster; projects: ProjectChoice[] }) {
  const router = useRouter();
  const { busy, error, run } = useAction();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("CHARACTER");
  const [source, setSource] = useState("");
  const [custom, setCustom] = useState(false);
  const [snapshotProject, setSnapshotProject] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const family = roster.families.find(
    (item) => item.title.toLocaleLowerCase() === source.trim().toLocaleLowerCase(),
  );
  const existing = family?.characters.find(
    (item) => item.display_name.toLocaleLowerCase() === name.trim().toLocaleLowerCase(),
  );
  return (
    <form
      className="surface panel form"
      onSubmit={async (event) => {
        event.preventDefault();
        const created = await run(() =>
          vaultFetch<CharacterSummary & { reused: boolean }>("library/characters/resolve", {
            json: {
              display_name: name,
              subject_kind: kind,
              source_label: source,
              origin: custom ? "PROJECT_ORIGINAL" : "SOURCE_WORK",
              project_key: custom ? snapshotProject || null : null,
              snapshot_project_key: snapshotProject || null,
              snapshot: snapshot.trim() ? { label: snapshot.trim() } : null,
            },
          }),
        );
        if (created) router.push(`/library/characters/${created.id}`);
      }}
    >
      <h3 style={{ margin: 0 }}>New character or creature</h3>
      <label className="row">
        <input type="checkbox" checked={custom} onChange={(event) => { setCustom(event.target.checked); setSource(event.target.checked ? "Original / Custom" : ""); }} />
        Custom / original character
      </label>
      <div className="form-row">
        <div className="field">
          <label>
            Family / series
            <input
              list="character-families"
              value={source}
              onChange={(event) => setSource(event.target.value)}
              placeholder="Search or browse held families"
              required
              style={{ width: "100%" }}
            />
            <datalist id="character-families">
              {roster.families.map((item) => <option key={item.key} value={item.title}>{[item.aliases.join(", "), Object.entries(item.availability).map(([medium, count]) => `${medium.toLowerCase()} ${count}`).join(" · ")].filter(Boolean).join(" · ")}</option>)}
            </datalist>
          </label>
        </div>
        <div className="field">
          <label>
            Name
            <input list="family-characters" value={name} onChange={(e) => setName(e.target.value)} required style={{ width: "100%" }} />
            <datalist id="family-characters">
              {(family?.characters ?? []).map((item) => <option key={item.id} value={item.display_name} />)}
            </datalist>
          </label>
        </div>
        <Select label="Kind" value={kind} onChange={setKind} options={SUBJECT_KINDS} />
      </div>
      {existing ? <p className="hint">Existing profile found. Continue will open it instead of creating a duplicate.</p> : null}
      <div className="form-row" style={{ gridTemplateColumns: "1fr 2fr" }}>
        <Select label="Project snapshot (optional)" value={snapshotProject} onChange={setSnapshotProject} options={[{ value: "", label: "None" }, ...projects.map((project) => ({ value: project.id, label: project.title }))]} />
        <div className="field"><label>Story version / era (optional)<input value={snapshot} onChange={(event) => setSnapshot(event.target.value)} placeholder="Arc, era, age, persistent state…" style={{ width: "100%" }} /></label></div>
      </div>
      <div className="row">
        <button className="button primary" type="submit" disabled={busy || !name.trim() || !source.trim() || (custom && !snapshotProject)}>
          {existing ? "Open existing" : "Create"}
        </button>
        <Feedback error={error} done={null} />
      </div>
    </form>
  );
}

export function EditCharacter({ character }: { character: CharacterSummary }) {
  const { busy, error, done, run } = useAction();
  const [values, setValues] = useState({
    summary: character.summary,
    scale_notes: character.scale_notes,
    distinguishing_marks: character.distinguishing_marks,
    posture_notes: character.posture_notes,
    notes: character.notes,
  });
  const field = (key: keyof typeof values, label: string) => (
    <div className="field">
      <label>
        {label}
        <textarea
          value={values[key]}
          onChange={(e) => setValues({ ...values, [key]: e.target.value })}
          style={{ width: "100%", minHeight: 60 }}
        />
      </label>
    </div>
  );
  return (
    <form
      className="surface panel stack"
      onSubmit={(event) => {
        event.preventDefault();
        run(
          () =>
            vaultFetch(`library/characters/${character.id}/update`, {
              json: { row_version: character.row_version, changes: values },
            }),
          "Saved.",
        );
      }}
    >
      <h3>Identity notes</h3>
      {field("summary", "Summary")}
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
        {field("scale_notes", "Scale and height")}
        {field("posture_notes", "Posture")}
      </div>
      {field("distinguishing_marks", "Distinguishing marks")}
      {field("notes", "Notes")}
      <div className="row">
        <button className="button small primary" type="submit" disabled={busy}>
          Save
        </button>
        <Feedback error={error} done={done} />
      </div>
    </form>
  );
}

export function AddOutfit({ characterId, projects }: { characterId: string; projects: ProjectChoice[] }) {
  const { busy, error, run } = useAction();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("SOURCE_DEFAULT");
  const [project, setProject] = useState(projects[0]?.id ?? "");
  const [era, setEra] = useState("");
  const [season, setSeason] = useState("");
  const [condition, setCondition] = useState("");
  return (
    <form
      className="surface panel stack"
      onSubmit={async (event) => {
        event.preventDefault();
        const saved = await run(() =>
          vaultFetch(`library/characters/${characterId}/outfits`, {
            json: {
              name,
              kind,
              project_key: kind === "PROJECT" ? project : null,
              era,
              season_weather: season,
              condition,
            },
          }),
        );
        if (saved) setName("");
      }}
    >
      <h3>Add an outfit</h3>
      <div className="form-row" style={{ gridTemplateColumns: "2fr 1fr 1fr" }}>
        <div className="field compact">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required style={{ width: "100%" }} />
          </label>
        </div>
        <Select label="Kind" value={kind} onChange={setKind} options={OUTFIT_KINDS} />
        {kind === "PROJECT" ? (
          <Select label="Project" value={project} onChange={setProject} options={projects.map((p) => ({ value: p.id, label: p.title }))} />
        ) : (
          <span />
        )}
      </div>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        <div className="field compact">
          <label>
            Era
            <input value={era} onChange={(e) => setEra(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Season / weather
            <input value={season} onChange={(e) => setSeason(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Condition
            <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="clean, torn, wet…" style={{ width: "100%" }} />
          </label>
        </div>
      </div>
      <div className="row">
        <button className="button small" type="submit" disabled={busy || !name.trim()}>
          Add outfit
        </button>
        <Feedback error={error} done={null} />
      </div>
    </form>
  );
}
