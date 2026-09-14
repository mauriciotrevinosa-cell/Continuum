"use client";

import { useState } from "react";
import {
  type CharacterSummary,
  MODE_CATEGORIES,
  MODE_SCOPES,
  MODE_TRIGGERS,
  type VisualMode,
  vaultFetch,
  words,
} from "@/lib/vault";
import { Select, type ProjectChoice } from "../_vault/SpecForm";
import { Feedback, useAction } from "../_vault/useAction";

export function CreateMode() {
  const { busy, error, run } = useAction();
  const [name, setName] = useState("");
  const [category, setCategory] = useState("EXPRESSIVE_COMEDY");
  const [description, setDescription] = useState("");
  return (
    <form
      className="surface panel stack"
      onSubmit={async (event) => {
        event.preventDefault();
        const saved = await run(() =>
          vaultFetch("library/visual-modes", { json: { name, category, description } }),
        );
        if (saved) {
          setName("");
          setDescription("");
        }
      }}
    >
      <h3>New visual mode</h3>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="field compact">
          <label>
            Name
            <input value={name} onChange={(e) => setName(e.target.value)} required placeholder="Comic squash" style={{ width: "100%" }} />
          </label>
        </div>
        <Select label="Category" value={category} onChange={setCategory} options={MODE_CATEGORIES} />
      </div>
      <div className="field">
        <label>
          How it looks
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Simplified proportions, big heads, flat tones; identity stays readable."
            style={{ width: "100%" }}
          />
        </label>
      </div>
      <div className="row">
        <button className="button small primary" type="submit" disabled={busy || !name.trim()}>
          Create mode
        </button>
        <Feedback error={error} done={null} />
      </div>
    </form>
  );
}

/**
 * Apply a mode to part of a project: a whole episode, a scene, a run of
 * pages, one panel, or an event. A character-controlled form (a character who
 * can choose to shrink) names the character; a scene-tone trigger is the
 * involuntary kind. Either way the character's identity record is unchanged.
 */
export function AssignMode({
  modes,
  projects,
  characters,
}: {
  modes: VisualMode[];
  projects: ProjectChoice[];
  characters: CharacterSummary[];
}) {
  const { busy, error, done, run } = useAction();
  const [project, setProject] = useState(projects[0]?.id ?? "");
  const [modeId, setModeId] = useState(modes[0]?.id ?? "");
  const [scope, setScope] = useState("SEQUENCE");
  const [trigger, setTrigger] = useState("DIRECTORIAL");
  const [episode, setEpisode] = useState("S1E1");
  const [scene, setScene] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [panel, setPanel] = useState("");
  const [event, setEvent] = useState("");
  const [characterId, setCharacterId] = useState("");
  const num = (v: string) => (v ? Number(v) : null);

  if (!projects.length || !modes.length) {
    return (
      <p className="hint">
        {modes.length ? "No projects are configured." : "Create a visual mode first."}
      </p>
    );
  }
  return (
    <form
      className="surface panel stack"
      onSubmit={(e) => {
        e.preventDefault();
        run(
          () =>
            vaultFetch(`projects/${project}/visual-modes`, {
              json: {
                visual_mode_id: modeId,
                scope,
                trigger,
                episode: scope === "EVENT" && !episode ? null : episode || null,
                scene: num(scene),
                page_from: num(from),
                page_to: num(to),
                panel: num(panel),
                event_label: event || null,
                character_id: characterId || null,
              },
            }),
          "Assigned.",
        );
      }}
    >
      <h3>Apply a mode to a project</h3>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
        <Select label="Project" value={project} onChange={setProject} options={projects.map((p) => ({ value: p.id, label: p.title }))} />
        <Select label="Mode" value={modeId} onChange={setModeId} options={modes.map((m) => ({ value: m.id, label: m.name }))} />
        <Select label="Scope" value={scope} onChange={setScope} options={MODE_SCOPES} />
        <Select label="Trigger" value={trigger} onChange={setTrigger} options={MODE_TRIGGERS} />
      </div>
      <div className="form-row" style={{ gridTemplateColumns: "repeat(5, minmax(0, 1fr))" }}>
        <div className="field compact">
          <label>
            Episode
            <input value={episode} onChange={(e) => setEpisode(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        {scope === "SCENE" ? (
          <div className="field compact">
            <label>
              Scene
              <input type="number" min={1} value={scene} onChange={(e) => setScene(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
        ) : null}
        {scope === "SEQUENCE" || scope === "PANEL" ? (
          <div className="field compact">
            <label>
              {scope === "PANEL" ? "Page" : "From page"}
              <input type="number" min={1} value={from} onChange={(e) => setFrom(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
        ) : null}
        {scope === "SEQUENCE" ? (
          <div className="field compact">
            <label>
              To page
              <input type="number" min={1} value={to} onChange={(e) => setTo(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
        ) : null}
        {scope === "PANEL" ? (
          <div className="field compact">
            <label>
              Panel
              <input type="number" min={1} value={panel} onChange={(e) => setPanel(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
        ) : null}
        {scope === "EVENT" ? (
          <div className="field compact">
            <label>
              Event
              <input value={event} onChange={(e) => setEvent(e.target.value)} placeholder="the reveal" style={{ width: "100%" }} />
            </label>
          </div>
        ) : null}
        <Select
          label={trigger === "CHARACTER_CONTROLLED" ? "Character (required)" : "Character"}
          value={characterId}
          onChange={setCharacterId}
          options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
          empty="Anyone in scope"
        />
      </div>
      <p className="hint">
        {trigger === "SCENE_TONE"
          ? "Involuntary: the scene's tone compresses whoever is in it."
          : trigger === "CHARACTER_CONTROLLED"
            ? "A form the character takes on purpose."
            : "A directorial choice for this part of the story."}{" "}
        The character&apos;s identity is not rewritten.
      </p>
      <div className="row">
        <button className="button small primary" type="submit" disabled={busy}>
          Apply {words(scope).toLowerCase()} mode
        </button>
        <Feedback error={error} done={done} />
      </div>
    </form>
  );
}

export function RemoveAssignment({ project, id }: { project: string; id: string }) {
  const { busy, error, run } = useAction();
  return (
    <>
      <button
        className="button small ghost danger"
        type="button"
        disabled={busy}
        onClick={() => run(() => vaultFetch(`projects/${project}/visual-modes/${id}/remove`, { json: {} }))}
      >
        Remove
      </button>
      {error ? <span className="error-text">{error}</span> : null}
    </>
  );
}
