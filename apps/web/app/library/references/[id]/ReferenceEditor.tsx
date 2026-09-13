"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ASPECTS,
  type CharacterSummary,
  DESCRIPTOR_FACETS,
  PANEL_SOURCE_ROLES,
  REFERENCE_CLASSES,
  REFERENCE_USES,
  type ReferenceView,
  STANDINGS,
  TECHNIQUE_FACETS,
  USER_ORIGINS,
  type VisualMode,
  vaultFetch,
  words,
} from "@/lib/vault";
import { Select, Toggles, type ProjectChoice, useOutfits } from "../../_vault/SpecForm";
import { Feedback, useAction } from "../../_vault/useAction";

function RemoveButton({ path, label }: { path: string; label: string }) {
  const { busy, error, run } = useAction();
  return (
    <>
      <button
        className="button small ghost danger"
        type="button"
        disabled={busy}
        aria-label={label}
        onClick={() => run(() => vaultFetch(path, { method: "POST", json: {} }))}
      >
        ✕
      </button>
      {error ? <span className="error-text">{error}</span> : null}
    </>
  );
}

/** Everything a person can decide about a reference after adding it. */
export function ReferenceEditor({
  reference,
  characters,
  modes,
  projects,
}: {
  reference: ReferenceView;
  characters: CharacterSummary[];
  modes: VisualMode[];
  projects: ProjectChoice[];
}) {
  const router = useRouter();
  const base = `library/references/${reference.id}`;
  const facts = useAction();
  const links = useAction();
  const [label, setLabel] = useState(reference.label);
  const [notes, setNotes] = useState(reference.notes);
  const [referenceClass, setReferenceClass] = useState(reference.reference_class);
  const [origin, setOrigin] = useState(reference.origin);
  const [creator, setCreator] = useState(reference.creator_handle ?? "");
  const [sourceUrl, setSourceUrl] = useState(reference.source_url ?? "");
  const [uses, setUses] = useState(reference.uses);
  const [characterId, setCharacterId] = useState("");
  const [aspect, setAspect] = useState("FACE");
  const [outfitId, setOutfitId] = useState("");
  const [facet, setFacet] = useState("PAGE_COMPOSITION");
  const [modeId, setModeId] = useState("");
  const [descriptorFacet, setDescriptorFacet] = useState("TAG");
  const [descriptorValue, setDescriptorValue] = useState("");
  const [projectKey, setProjectKey] = useState(projects[0]?.id ?? "");
  const [standing, setStanding] = useState("USEFUL");
  const [episode, setEpisode] = useState("S1E1");
  const [page, setPage] = useState("");
  const [panel, setPanel] = useState("");
  const [role, setRole] = useState("COMPOSITION");
  const outfits = useOutfits(characterId);
  const generated = reference.origin === "GENERATED" || reference.origin === "PROJECT_APPROVED";

  const saveFacts = () =>
    facts.run(async () => {
      const changes: Record<string, unknown> = {
        label,
        notes,
        reference_class: referenceClass,
        creator_handle: creator,
        source_url: sourceUrl,
      };
      if (!generated) changes.origin = origin;
      await vaultFetch(`${base}/update`, { json: { row_version: reference.row_version, changes } });
      await vaultFetch(`${base}/uses`, { json: { uses } });
    }, "Saved.");

  if (reference.removed) {
    return (
      <div className="banner">
        <p>
          <strong>Removed from the catalog.</strong> It stays visible here because attempts may
          still name it; the original file was never touched.
        </p>
      </div>
    );
  }

  return (
    <div className="stack">
      <section className="surface panel stack" aria-labelledby="facts">
        <h3 id="facts">What it is</h3>
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <Select label="Class" value={referenceClass} onChange={setReferenceClass} options={REFERENCE_CLASSES} />
          {generated ? (
            <div className="field compact">
              <span className="label">Origin</span>
              <span>{words(reference.origin)} (set by production)</span>
            </div>
          ) : (
            <Select label="Origin" value={origin} onChange={setOrigin} options={USER_ORIGINS} />
          )}
        </div>
        <div className="field compact">
          <label>
            Label
            <input value={label} onChange={(e) => setLabel(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
          <div className="field compact">
            <label>
              Creator handle
              <input value={creator} onChange={(e) => setCreator(e.target.value)} placeholder="@artist" style={{ width: "100%" }} />
            </label>
          </div>
          <div className="field compact">
            <label>
              Link (kept, never fetched)
              <input value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://" style={{ width: "100%" }} />
            </label>
          </div>
        </div>
        <div className="field">
          <span className="label">Intended uses</span>
          <Toggles values={REFERENCE_USES} selected={uses} onChange={setUses} label="Intended uses" />
        </div>
        <div className="field">
          <label>
            Notes
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="row">
          <button className="button primary small" type="button" disabled={facts.busy} onClick={saveFacts}>
            Save
          </button>
          <button
            className="button small ghost"
            type="button"
            disabled={facts.busy}
            onClick={() =>
              facts.run(() =>
                vaultFetch(`${base}/update`, {
                  json: { row_version: reference.row_version, changes: { favorite: !reference.favorite } },
                }),
              )
            }
          >
            {reference.favorite ? "★ Unfavorite" : "☆ Favorite"}
          </button>
          <Feedback error={facts.error} done={facts.done} />
        </div>
      </section>

      <section className="surface panel stack" aria-labelledby="characters">
        <h3 id="characters">Characters</h3>
        {reference.characters.map((link) => (
          <div className="op-item" key={link.link_id}>
            <span>
              <b>{link.character_name}</b> · {words(link.group)} · {words(link.aspect)}
              {link.outfit_name ? ` · ${link.outfit_name}` : ""}
            </span>
            <span className="row">
              <button
                className="button small ghost"
                type="button"
                onClick={() =>
                  links.run(() =>
                    vaultFetch(`library/reference-characters/${link.link_id}/preferred`, {
                      json: { preferred: !link.preferred },
                    }),
                  )
                }
              >
                {link.preferred ? "Preferred ✓" : "Make preferred"}
              </button>
              <RemoveButton path={`library/reference-characters/${link.link_id}/remove`} label="Unlink" />
            </span>
          </div>
        ))}
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr auto", alignItems: "end" }}>
          <Select
            label="Character"
            value={characterId}
            onChange={(v) => {
              setCharacterId(v);
              setOutfitId("");
            }}
            options={characters.map((c) => ({ value: c.id, label: c.display_name }))}
            empty="Choose…"
          />
          <Select
            label="Aspect"
            value={aspect}
            onChange={setAspect}
            options={[...ASPECTS.IDENTITY, ...ASPECTS.WARDROBE, ...ASPECTS.ACTING]}
          />
          <Select
            label="Outfit"
            value={outfitId}
            onChange={setOutfitId}
            options={outfits.map((o) => ({ value: o.id, label: o.name }))}
            empty="None"
          />
          <button
            className="button small"
            type="button"
            disabled={!characterId || links.busy}
            onClick={() =>
              links.run(() =>
                vaultFetch(`${base}/characters`, {
                  json: { character_id: characterId, aspect, outfit_id: outfitId || null },
                }),
              )
            }
          >
            Link
          </button>
        </div>
      </section>

      <section className="surface panel stack" aria-labelledby="technique">
        <h3 id="technique">Technique and visual modes</h3>
        {reference.techniques.map((t) => (
          <div className="op-item" key={t.link_id}>
            <span>
              {words(t.facet)}
              {t.visual_mode_name ? ` · ${t.visual_mode_name}` : ""}
            </span>
            <RemoveButton path={`library/reference-techniques/${t.link_id}/remove`} label="Remove technique" />
          </div>
        ))}
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
          <Select label="Technique" value={facet} onChange={setFacet} options={TECHNIQUE_FACETS} />
          <Select
            label="Visual mode"
            value={modeId}
            onChange={setModeId}
            options={modes.map((m) => ({ value: m.id, label: m.name }))}
            empty="None"
          />
          <button
            className="button small"
            type="button"
            disabled={links.busy}
            onClick={() =>
              links.run(() =>
                vaultFetch(`${base}/techniques`, { json: { facet, visual_mode_id: modeId || null } }),
              )
            }
          >
            Add
          </button>
        </div>
      </section>

      <section className="surface panel stack" aria-labelledby="descriptors">
        <h3 id="descriptors">Descriptors</h3>
        {reference.descriptors.map((d) => (
          <div className="op-item" key={d.id}>
            <span>
              <span className={`chip tiny plain ${d.origin === "USER" ? "accent" : "info"}`}>{d.origin_label}</span>{" "}
              {words(d.facet)}: <b>{d.value}</b>
              {d.analyzer_ref ? <span className="muted"> · {d.analyzer_ref}</span> : null}
            </span>
            <RemoveButton path={`library/reference-descriptors/${d.id}/remove`} label="Remove descriptor" />
          </div>
        ))}
        <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
          <Select label="Facet" value={descriptorFacet} onChange={setDescriptorFacet} options={DESCRIPTOR_FACETS} />
          <div className="field compact">
            <label>
              Value
              <input value={descriptorValue} onChange={(e) => setDescriptorValue(e.target.value)} style={{ width: "100%" }} />
            </label>
          </div>
          <button
            className="button small"
            type="button"
            disabled={!descriptorValue.trim() || links.busy}
            onClick={async () => {
              const saved = await links.run(() =>
                vaultFetch(`${base}/descriptors`, { json: { facet: descriptorFacet, value: descriptorValue } }),
              );
              if (saved) setDescriptorValue("");
            }}
          >
            Tag
          </button>
        </div>
        <p className="hint">Tags you add are USER TAGGED. Only an analyzer adds ANALYSIS DERIVED descriptors.</p>
      </section>

      <section className="surface panel stack" aria-labelledby="projects">
        <h3 id="projects">In projects</h3>
        {reference.standings.map((s) => (
          <div className="op-item" key={s.id}>
            <span>
              {s.project_key} · {words(s.standing)}
            </span>
            <RemoveButton path={`library/reference-standings/${s.id}/remove`} label="Remove standing" />
          </div>
        ))}
        {reference.panel_sources.map((p) => (
          <div className="op-item" key={p.id}>
            <span>
              {p.project_key} · {p.episode} · page {p.page}
              {p.panel ? ` · panel ${p.panel}` : ""} · {words(p.role)}
            </span>
            <RemoveButton path={`library/panel-sources/${p.id}/remove`} label="Remove scene source" />
          </div>
        ))}
        {projects.length ? (
          <>
            <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr auto", alignItems: "end" }}>
              <Select label="Project" value={projectKey} onChange={setProjectKey} options={projects.map((p) => ({ value: p.id, label: p.title }))} />
              <Select label="Standing" value={standing} onChange={setStanding} options={STANDINGS} />
              <button
                className="button small"
                type="button"
                disabled={links.busy}
                onClick={() => links.run(() => vaultFetch(`${base}/standings`, { json: { project_key: projectKey, standing } }))}
              >
                Set
              </button>
            </div>
            <div className="form-row" style={{ gridTemplateColumns: "1fr 80px 80px 1fr auto", alignItems: "end" }}>
              <div className="field compact">
                <label>
                  Episode
                  <input value={episode} onChange={(e) => setEpisode(e.target.value)} style={{ width: "100%" }} />
                </label>
              </div>
              <div className="field compact">
                <label>
                  Page
                  <input type="number" min={1} value={page} onChange={(e) => setPage(e.target.value)} style={{ width: "100%" }} />
                </label>
              </div>
              <div className="field compact">
                <label>
                  Panel
                  <input type="number" min={1} value={panel} onChange={(e) => setPanel(e.target.value)} style={{ width: "100%" }} />
                </label>
              </div>
              <Select label="Role" value={role} onChange={setRole} options={PANEL_SOURCE_ROLES} />
              <button
                className="button small"
                type="button"
                disabled={!page || links.busy}
                onClick={() =>
                  links.run(() =>
                    vaultFetch(`${base}/panel-sources`, {
                      json: {
                        project_key: projectKey,
                        episode,
                        page: Number(page),
                        panel: panel ? Number(panel) : null,
                        role,
                      },
                    }),
                  )
                }
              >
                Use for scene
              </button>
            </div>
          </>
        ) : (
          <p className="hint">No projects are configured.</p>
        )}
      </section>
      <Feedback error={links.error} done={null} />

      <section className="panel">
        <button
          className="button small ghost danger"
          type="button"
          disabled={facts.busy}
          onClick={async () => {
            if (!window.confirm("Remove this reference from the catalog? The original file is not touched.")) return;
            const removed = await facts.run(() =>
              vaultFetch(`${base}/remove`, { json: { row_version: reference.row_version } }),
            );
            if (removed) router.push("/library/references");
          }}
        >
          Remove from catalog
        </button>
      </section>
    </div>
  );
}
