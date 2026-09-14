"use client";

import { useEffect, useState } from "react";
import {
  ASPECTS,
  type CharacterSummary,
  type CharacterVault,
  PANEL_SOURCE_ROLES,
  REFERENCE_CLASSES,
  REFERENCE_USES,
  STANDINGS,
  TECHNIQUE_FACETS,
  USER_ORIGINS,
  type VisualMode,
  vaultFetch,
  words,
} from "@/lib/vault";

export interface ProjectChoice {
  id: string;
  title: string;
}

/** The body of a ReferenceSpec, as the API accepts it. */
export interface SpecBody {
  reference_class: string;
  origin: string;
  label: string;
  notes: string;
  favorite: boolean;
  uses: string[];
  characters: { character_id: string; aspect: string; outfit_id: string | null; preferred: boolean }[];
  techniques: { facet: string; visual_mode_id: string | null }[];
  descriptors: { facet: string; value: string }[];
  standings: { project_key: string; standing: string; character_id: string | null }[];
  panel_sources: {
    project_key: string;
    episode: string;
    page: number;
    panel: number | null;
    chapter: number | null;
    role: string;
  }[];
}

type Tab = "character" | "style" | "scene";

const TAB_DEFAULTS: Record<Tab, { reference_class: string; uses: string[] }> = {
  character: { reference_class: "CANON", uses: ["IDENTITY"] },
  style: { reference_class: "TECHNIQUE", uses: ["STYLE"] },
  scene: { reference_class: "CANON", uses: ["SCENE_SOURCE"] },
};

export function Toggles({
  values,
  selected,
  onChange,
  label,
}: {
  values: readonly string[];
  selected: string[];
  onChange: (next: string[]) => void;
  label: string;
}) {
  return (
    <div className="toggles" role="group" aria-label={label}>
      {values.map((value) => {
        const on = selected.includes(value);
        return (
          <button
            key={value}
            type="button"
            className="toggle"
            aria-pressed={on}
            onClick={() => onChange(on ? selected.filter((v) => v !== value) : [...selected, value])}
          >
            {words(value)}
          </button>
        );
      })}
    </div>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  empty,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: readonly (string | { value: string; label: string })[];
  empty?: string;
}) {
  return (
    <div className="field compact">
      <label>
        {label}
        <select value={value} onChange={(event) => onChange(event.target.value)} style={{ width: "100%" }}>
          {empty !== undefined ? <option value="">{empty}</option> : null}
          {options.map((option) =>
            typeof option === "string" ? (
              <option key={option} value={option}>
                {words(option)}
              </option>
            ) : (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ),
          )}
        </select>
      </label>
    </div>
  );
}

/** Outfits of one character, loaded when the character is chosen. */
export function useOutfits(characterId: string) {
  const [outfits, setOutfits] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    let live = true;
    if (!characterId) {
      setOutfits([]);
      return;
    }
    vaultFetch<CharacterVault>(`library/characters/${characterId}`)
      .then((v) => live && setOutfits(v.wardrobe.outfits.map((o) => ({ id: o.id, name: o.name }))))
      .catch(() => live && setOutfits([]));
    return () => {
      live = false;
    };
  }, [characterId]);
  return outfits;
}

/**
 * What a new reference is and what it is for - character, style or scene
 * source - decided in one step, while looking at the page.
 */
export function SpecForm({
  characters,
  modes,
  projects,
  busy,
  submitLabel,
  onSubmit,
  defaultOrigin = "SOURCE",
  page,
}: {
  characters: CharacterSummary[];
  modes: VisualMode[];
  projects: ProjectChoice[];
  busy: boolean;
  submitLabel: string;
  onSubmit: (spec: SpecBody) => void;
  defaultOrigin?: string;
  page?: number | null;
}) {
  const [tab, setTab] = useState<Tab>("character");
  const [referenceClass, setReferenceClass] = useState("CANON");
  const [origin, setOrigin] = useState(defaultOrigin);
  const [label, setLabel] = useState("");
  const [notes, setNotes] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [uses, setUses] = useState<string[]>(["IDENTITY"]);
  const [characterId, setCharacterId] = useState("");
  const [aspect, setAspect] = useState("FACE");
  const [outfitId, setOutfitId] = useState("");
  const [preferred, setPreferred] = useState(false);
  const [facet, setFacet] = useState("PAGE_COMPOSITION");
  const [modeId, setModeId] = useState("");
  const [tags, setTags] = useState("");
  const [shot, setShot] = useState("");
  const [projectKey, setProjectKey] = useState(projects[0]?.id ?? "");
  const [standing, setStanding] = useState("");
  const [episode, setEpisode] = useState("S1E1");
  const [targetPage, setTargetPage] = useState("");
  const [panel, setPanel] = useState("");
  const [chapter, setChapter] = useState("");
  const [role, setRole] = useState("SOURCE_PLATE");
  const outfits = useOutfits(characterId);

  const choose = (next: Tab) => {
    setTab(next);
    setReferenceClass(TAB_DEFAULTS[next].reference_class);
    setUses(TAB_DEFAULTS[next].uses);
  };

  const build = (): SpecBody => {
    const descriptors = tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
      .map((value) => ({ facet: "TAG", value }));
    if (shot.trim()) descriptors.push({ facet: "SHOT_TYPE", value: shot.trim() });
    const spec: SpecBody = {
      reference_class: referenceClass,
      origin,
      label,
      notes,
      favorite,
      uses,
      characters: [],
      techniques: [],
      descriptors,
      standings: [],
      panel_sources: [],
    };
    if (tab === "character" && characterId) {
      spec.characters.push({
        character_id: characterId,
        aspect,
        outfit_id: outfitId || null,
        preferred,
      });
    }
    if (tab === "style") spec.techniques.push({ facet, visual_mode_id: modeId || null });
    if (projectKey && standing) {
      spec.standings.push({
        project_key: projectKey,
        standing,
        character_id: tab === "character" && characterId ? characterId : null,
      });
    }
    if (tab === "scene" && projectKey && targetPage) {
      spec.panel_sources.push({
        project_key: projectKey,
        episode,
        page: Number(targetPage),
        panel: panel ? Number(panel) : null,
        chapter: chapter ? Number(chapter) : null,
        role,
      });
    }
    return spec;
  };

  return (
    <form
      className="stack"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(build());
      }}
    >
      <div className="tabs" role="tablist" aria-label="Add as">
        {(["character", "style", "scene"] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} onClick={() => choose(t)}>
            {t === "character" ? "Character" : t === "style" ? "Style" : "Scene source"}
          </button>
        ))}
      </div>

      {tab === "character" ? (
        <div className="stack">
          <Select
            label="Character"
            value={characterId}
            onChange={(v) => {
              setCharacterId(v);
              setOutfitId("");
            }}
            options={characters.map((c) => ({ value: c.id, label: `${c.display_name}${c.subject_kind !== "CHARACTER" ? ` (${words(c.subject_kind)})` : ""}` }))}
            empty={characters.length ? "Choose…" : "Create a character first"}
          />
          <Select
            label="Aspect"
            value={aspect}
            onChange={setAspect}
            options={[
              ...ASPECTS.IDENTITY.map((a) => ({ value: a, label: `Identity · ${words(a)}` })),
              ...ASPECTS.WARDROBE.map((a) => ({ value: a, label: `Wardrobe · ${words(a)}` })),
              ...ASPECTS.ACTING.map((a) => ({ value: a, label: `Acting · ${words(a)}` })),
            ]}
          />
          {characterId ? (
            <Select
              label="Outfit"
              value={outfitId}
              onChange={setOutfitId}
              options={outfits.map((o) => ({ value: o.id, label: o.name }))}
              empty="No particular outfit"
            />
          ) : null}
          <label className="check">
            <input type="checkbox" checked={preferred} onChange={(e) => setPreferred(e.target.checked)} />
            Preferred for this aspect
          </label>
        </div>
      ) : tab === "style" ? (
        <div className="stack">
          <Select label="Technique" value={facet} onChange={setFacet} options={TECHNIQUE_FACETS} />
          <Select
            label="Visual mode"
            value={modeId}
            onChange={setModeId}
            options={modes.map((m) => ({ value: m.id, label: `${m.name} · ${words(m.category)}` }))}
            empty="Not tied to a mode"
          />
          <p className="hint">Technique stays separate from who is drawn: no character is changed.</p>
        </div>
      ) : (
        <div className="stack">
          <Select
            label="Project"
            value={projectKey}
            onChange={setProjectKey}
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
            empty={projects.length ? undefined : "No projects"}
          />
          <div className="form-row" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
            <div className="field compact">
              <label>
                Episode
                <input value={episode} onChange={(e) => setEpisode(e.target.value)} style={{ width: "100%" }} />
              </label>
            </div>
            <div className="field compact">
              <label>
                Chapter
                <input type="number" min={1} value={chapter} onChange={(e) => setChapter(e.target.value)} style={{ width: "100%" }} />
              </label>
            </div>
            <div className="field compact">
              <label>
                Page
                <input type="number" min={1} required value={targetPage} onChange={(e) => setTargetPage(e.target.value)} style={{ width: "100%" }} />
              </label>
            </div>
            <div className="field compact">
              <label>
                Panel
                <input type="number" min={1} value={panel} onChange={(e) => setPanel(e.target.value)} style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <Select label="Role" value={role} onChange={setRole} options={PANEL_SOURCE_ROLES} />
          <p className="hint">
            A source plate may later be edited into a new rough; the page itself is never changed.
          </p>
        </div>
      )}

      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <Select label="Class" value={referenceClass} onChange={setReferenceClass} options={REFERENCE_CLASSES} />
        <Select label="Origin" value={origin} onChange={setOrigin} options={USER_ORIGINS} />
      </div>
      <div className="field">
        <span className="label">Intended uses</span>
        <Toggles values={REFERENCE_USES} selected={uses} onChange={setUses} label="Intended uses" />
      </div>
      <div className="field compact">
        <label>
          Label
          <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder={page !== undefined && page !== null ? `Page ${page + 1}` : ""} style={{ width: "100%" }} />
        </label>
      </div>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="field compact">
          <label>
            Tags (USER TAGGED)
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="night, rain" style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Shot type
            <input value={shot} onChange={(e) => setShot(e.target.value)} placeholder="close-up" style={{ width: "100%" }} />
          </label>
        </div>
      </div>
      {tab !== "scene" && projects.length ? (
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <Select
            label="Project"
            value={projectKey}
            onChange={setProjectKey}
            options={projects.map((p) => ({ value: p.id, label: p.title }))}
          />
          <Select
            label="Project standing"
            value={standing}
            onChange={setStanding}
            options={STANDINGS}
            empty="None"
          />
        </div>
      ) : null}
      <div className="field">
        <label>
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: "100%" }} />
        </label>
      </div>
      <label className="check">
        <input type="checkbox" checked={favorite} onChange={(e) => setFavorite(e.target.checked)} />
        Favorite
      </label>
      <button className="button primary" type="submit" disabled={busy}>
        {busy ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}
