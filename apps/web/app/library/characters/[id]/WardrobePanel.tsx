"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { type Outfit, vaultFetch, words } from "@/lib/vault";
import { Feedback, useAction } from "../../_vault/useAction";

interface CharacterChoice {
  id: string;
  name: string;
}

interface ProjectChoice {
  id: string;
  title: string;
}

const REVIEW_DECISIONS = ["DRAFT", "REVIEW", "APPROVED", "REJECTED"] as const;

/**
 * Timeline-aware wardrobe controls: review a project-created outfit, and
 * record who wears a garment in a story stage. The owner is the outfit's
 * character; a borrowed garment keeps its owner and never clones identity.
 * The project is chosen from existing project data, never hardcoded.
 */
export function WardrobePanel({
  outfits,
  characters,
  projects,
}: {
  outfits: Outfit[];
  characters: CharacterChoice[];
  projects: ProjectChoice[];
}) {
  const router = useRouter();
  const action = useAction();
  const [reviewer, setReviewer] = useState("");
  const [project, setProject] = useState(projects[0]?.id ?? "");
  const [wearOutfit, setWearOutfit] = useState("");
  const [wearer, setWearer] = useState("");
  const [stage, setStage] = useState("");
  const [context, setContext] = useState("");
  const [condition, setCondition] = useState("");

  const review = (id: string, decision: string) =>
    action.run(async () => {
      await vaultFetch(`library/outfits/${id}/review`, {
        json: { decision, reviewer, notes: "" },
      });
      router.refresh();
    }, "Review saved.");

  const assignWear = () =>
    action.run(async () => {
      await vaultFetch(`library/outfits/${wearOutfit}/wear`, {
        json: { wearer_character_id: wearer, project_key: project, stage, context, condition },
      });
      setStage("");
      setContext("");
      setCondition("");
      router.refresh();
    }, "Wear recorded.");

  const projectOutfits = outfits.filter((o) => o.kind === "PROJECT");

  return (
    <div className="stack">
      {projectOutfits.length ? (
        <div className="surface panel stack">
          <span className="eyebrow" style={{ margin: 0 }}>
            Project outfit review <span className="muted">· never self-approves</span>
          </span>
          {projectOutfits.map((outfit) => (
            <div key={outfit.id} className="row" style={{ gap: 6 }}>
              <span className="sub" style={{ flex: 1 }}>
                {outfit.name}
                {outfit.review_status ? (
                  <span className={`chip ${outfit.review_status === "APPROVED" ? "ok" : outfit.review_status === "REJECTED" ? "err" : "warn"} tiny`} style={{ marginLeft: 8 }}>
                    {words(outfit.review_status)}
                  </span>
                ) : (
                  <span className="chip quiet tiny" style={{ marginLeft: 8 }}>unreviewed</span>
                )}
              </span>
              <input aria-label="Reviewer name" placeholder="Reviewer" value={reviewer} onChange={(e) => setReviewer(e.target.value)} style={{ width: 120 }} />
              {REVIEW_DECISIONS.map((d) => (
                <button
                  key={d}
                  className="button small ghost"
                  type="button"
                  disabled={action.busy || !reviewer.trim()}
                  onClick={() => review(outfit.id, d)}
                >
                  {words(d)}
                </button>
              ))}
            </div>
          ))}
        </div>
      ) : null}

      {projectOutfits.length ? (
        <div className="surface panel stack" style={{ background: "var(--surface-2)" }}>
          <span className="eyebrow" style={{ margin: 0 }}>
            Record who wears a garment <span className="muted">· owner vs wearer</span>
          </span>
          <p className="hint" style={{ margin: 0 }}>
            A garment keeps its owner. Assigning a different wearer for a story stage records
            borrowing without cloning identity or rewriting earlier continuity.
          </p>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr" }}>
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
                Garment
                <select value={wearOutfit} onChange={(e) => setWearOutfit(e.target.value)} style={{ width: "100%" }}>
                  <option value="">Choose</option>
                  {projectOutfits.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="field compact">
              <label>
                Worn by
                <select value={wearer} onChange={(e) => setWearer(e.target.value)} style={{ width: "100%" }}>
                  <option value="">Choose</option>
                  {characters.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="field compact">
              <label>
                Stage
                <input value={stage} onChange={(e) => setStage(e.target.value)} placeholder="E14, EARLY_ARRIVAL" style={{ width: "100%" }} />
              </label>
            </div>
            <div className="field compact">
              <label>
                Context
                <input value={context} onChange={(e) => setContext(e.target.value)} placeholder="borrowed after reconciliation" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
            <div className="field compact">
              <label>
                Condition (this stage)
                <input value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="clean, dirty, damaged, repaired…" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <div className="row">
            <button className="button small primary" type="button" disabled={action.busy || !wearOutfit || !wearer || !stage.trim() || !project} onClick={assignWear}>
              Record wear
            </button>
            <Feedback error={action.error} done={action.done} />
          </div>
        </div>
      ) : null}
    </div>
  );
}