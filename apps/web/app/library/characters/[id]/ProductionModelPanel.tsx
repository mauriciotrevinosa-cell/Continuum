"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { type Observation, type ProductionModel } from "@/lib/manga";
import { vaultFetch, words } from "@/lib/vault";
import { Feedback, useAction } from "../../_vault/useAction";

const EVIDENCE_ROLES = ["IDENTITY", "BODY", "WARDROBE", "EXPRESSION", "POSE", "ACCESSORY", "SCALE"] as const;

interface ProjectChoice {
  id: string;
  title: string;
}

interface OutfitChoice {
  id: string;
  name: string;
}

/**
 * Create, review and approve a project-scoped Production Model for one
 * character. The model is a small, human-approved identity lock; it never
 * self-approves and never replaces the corpus.
 */
export function ProductionModelPanel({
  characterId,
  projects,
  outfits,
  models,
}: {
  characterId: string;
  projects: ProjectChoice[];
  outfits: OutfitChoice[];
  models: ProductionModel[];
}) {
  const router = useRouter();
  const action = useAction();
  const [reviewer, setReviewer] = useState("");
  const [project, setProject] = useState(projects[0]?.id ?? "");
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [identityRules, setIdentityRules] = useState("");
  const [restrictions, setRestrictions] = useState("");
  const [outfitId, setOutfitId] = useState("");

  const create = () =>
    action.run(async () => {
      await vaultFetch(`library/characters/${characterId}/production-models`, {
        json: {
          project_key: project,
          name,
          summary,
          identity_rules: identityRules.split(",").map((s) => s.trim()).filter(Boolean),
          restrictions: restrictions.split(",").map((s) => s.trim()).filter(Boolean),
          active_outfit_id: outfitId || null,
        },
      });
      setName("");
      setSummary("");
      setIdentityRules("");
      setRestrictions("");
      router.refresh();
    }, "Production model created as DRAFT.");

  const submit = (id: string) =>
    action.run(async () => {
      await vaultFetch(`library/character-production-models/${id}/submit`, { method: "POST" });
      router.refresh();
    }, "Submitted for review.");

  const approve = (id: string) =>
    action.run(async () => {
      await vaultFetch(`library/character-production-models/${id}/approve`, {
        json: { reviewer },
      });
      router.refresh();
    }, "Approved. It now guides rendering for this project.");

  const sorted = [...models].sort((a, b) => b.version - a.version);

  return (
    <section className="block" aria-label="Production model management">
      <div className="block-head">
        <h2>
          Production model <small>create, review, approve</small>
        </h2>
      </div>
      <div className="surface panel stack">
        <p className="hint">
          A production model is a small, versioned identity lock for one project. Add confirmed
          evidence, submit for review, then a person approves it. Approved evidence is preferred
          before general corpus evidence in page bundles.
        </p>

        <div className="surface panel stack" style={{ background: "var(--surface-2)" }}>
          <h3 style={{ margin: 0 }}>New production model</h3>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="field compact">
              <label>
                Project
                <select value={project} onChange={(e) => setProject(e.target.value)} style={{ width: "100%" }}>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="field compact">
              <label>
                Name
                <input value={name} onChange={(e) => setName(e.target.value)} placeholder="The Arrivals Production Model v1" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <div className="field compact">
            <label>
              Summary
              <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="What this version locks" style={{ width: "100%" }} />
            </label>
          </div>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="field compact">
              <label>
                Identity rules (comma separated)
                <input value={identityRules} onChange={(e) => setIdentityRules(e.target.value)} placeholder="deep-brown wavy hair, no glasses" style={{ width: "100%" }} />
              </label>
            </div>
            <div className="field compact">
              <label>
                Restrictions (comma separated)
                <input value={restrictions} onChange={(e) => setRestrictions(e.target.value)} placeholder="no glasses" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <div className="field compact">
            <label>
              Active outfit (optional)
              <select value={outfitId} onChange={(e) => setOutfitId(e.target.value)} style={{ width: "100%" }}>
                <option value="">None</option>
                {outfits.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="row">
            <button className="button small primary" type="button" disabled={action.busy || !name.trim() || !project} onClick={create}>
              Create DRAFT model
            </button>
            <Feedback error={action.error} done={action.done} />
          </div>
        </div>

        {sorted.length ? (
          <div className="stack">
            <span className="eyebrow" style={{ margin: 0 }}>
              Versions
            </span>
            {sorted.map((model) => (
              <ModelRow
                key={model.id}
                characterId={characterId}
                model={model}
                reviewer={reviewer}
                setReviewer={setReviewer}
                busy={action.busy}
                onSubmit={() => submit(model.id)}
                onApprove={() => approve(model.id)}
              />
            ))}
          </div>
        ) : (
          <p className="hint">No production model yet. Create one above, then add evidence.</p>
        )}
      </div>
    </section>
  );
}

function ModelRow({
  characterId,
  model,
  reviewer,
  setReviewer,
  busy,
  onSubmit,
  onApprove,
}: {
  characterId: string;
  model: ProductionModel;
  reviewer: string;
  setReviewer: (value: string) => void;
  busy: boolean;
  onSubmit: () => void;
  onApprove: () => void;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const tone = model.status === "APPROVED" ? "ok" : model.status === "REVIEW" ? "accent" : model.status === "SUPERSEDED" ? "quiet" : "info";
  return (
    <div className="surface panel stack" style={{ background: "var(--surface-2)" }}>
      <div className="spread">
        <div>
          <span className="row" style={{ gap: 6 }}>
            <span className={`chip ${tone} tiny`}>{words(model.status)}</span>
            <span className="chip quiet tiny">v{model.version}</span>
            <span className="chip quiet tiny">{model.project_key}</span>
          </span>
          <h3 style={{ margin: "4px 0 0" }}>{model.name}</h3>
        </div>
        <span className="muted">{model.evidence.length} evidence links</span>
      </div>
      {model.summary ? <p className="hint" style={{ margin: 0 }}>{model.summary}</p> : null}
      {model.identity_rules.length ? <p className="sub" style={{ margin: 0 }}><strong>Identity:</strong> {model.identity_rules.join(" · ")}</p> : null}
      {model.restrictions.length ? <p className="sub" style={{ margin: 0 }}><strong>Never:</strong> {model.restrictions.join(" · ")}</p> : null}
      {model.approved_by ? <p className="muted" style={{ margin: 0 }}>Approved by {model.approved_by}</p> : null}

      {model.status === "DRAFT" || model.status === "REVIEW" ? (
        <div className="row" style={{ gap: 6 }}>
          <button className="button small ghost" type="button" onClick={() => setShowEvidence((v) => !v)}>
            {showEvidence ? "Hide evidence" : "Add evidence"}
          </button>
          {model.status === "DRAFT" ? (
            <button className="button small primary" type="button" disabled={busy || !model.evidence.length} onClick={onSubmit}>
              Submit for review
            </button>
          ) : (
            <div className="row" style={{ gap: 6 }}>
              <input aria-label="Reviewer name" placeholder="Reviewer name" value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ width: 160 }} />
              <button className="button small primary" type="button" disabled={busy || !reviewer.trim()} onClick={onApprove}>
                Approve
              </button>
            </div>
          )}
        </div>
      ) : null}

      {showEvidence ? <EvidenceAdder characterId={characterId} model={model} /> : null}
    </div>
  );
}

function EvidenceAdder({ characterId, model }: { characterId: string; model: ProductionModel }) {
  const router = useRouter();
  const action = useAction();
  const [observations, setObservations] = useState<Observation[] | null>(null);
  const [role, setRole] = useState<string>("IDENTITY");
  const [preferred, setPreferred] = useState(false);

  const load = () =>
    action.run(async () => {
      const found = await vaultFetch<{ observations: Observation[] }>(
        `library/characters/${characterId}/observations`,
        { query: { status: "CONFIRMED", limit: 200 } },
      );
      setObservations(found.observations);
    });

  const add = (observationId: string) =>
    action.run(async () => {
      await vaultFetch(`library/character-production-models/${model.id}/evidence`, {
        json: { observation_id: observationId, role, preferred, required: false, position: 0, notes: "" },
      });
      router.refresh();
    }, "Evidence added.");

  const existing = new Set(model.evidence.map((e) => e.observation_id));

  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row" style={{ gap: 6 }}>
        <select aria-label="Evidence role" value={role} onChange={(e) => setRole(e.target.value)}>
          {EVIDENCE_ROLES.map((r) => (
            <option key={r} value={r}>
              {words(r)}
            </option>
          ))}
        </select>
        <label className="check">
          <input type="checkbox" checked={preferred} onChange={(e) => setPreferred(e.target.checked)} /> Preferred
        </label>
        {observations === null ? (
          <button className="button small ghost" type="button" disabled={action.busy} onClick={load}>
            Load confirmed observations
          </button>
        ) : null}
      </div>
      <Feedback error={action.error} done={action.done} />
      {observations ? (
        observations.length ? (
          <div className="list">
            {observations.map((o) => (
              <div className="list-item" key={o.id}>
                <div>
                  <span className="sub">{o.source_label || o.locator}</span>
                  <span className="muted"> · {o.facets.map((f) => words(f)).join(", ") || "no facets"}</span>
                </div>
                {existing.has(o.id) ? (
                  <span className="side muted">already linked</span>
                ) : (
                  <button className="button small ghost" type="button" disabled={action.busy} onClick={() => add(o.id)}>
                    Add as {words(role)}
                  </button>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">No confirmed observations yet. Confirm observations in the corpus first.</p>
        )
      ) : null}
    </div>
  );
}