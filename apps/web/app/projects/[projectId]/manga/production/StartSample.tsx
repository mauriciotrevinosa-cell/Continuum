"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { Backend, PageBody, Profile, RunView } from "@/lib/manga";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../../library/_vault/useAction";

interface Insertion {
  item_key: string;
  text?: string;
  conflict?: string | null;
  source_beats?: { number: number; title: string }[];
}

interface Materialized {
  id: string;
  hash: string;
  body: {
    page_count: number;
    chapter_cut: { first_page: number; last_page: number; summary: string } | null;
    pages: PageBody[];
    insertions: { placed_in_chapter: Insertion[]; unplaced: Insertion[] };
    warnings: string[];
  };
}

export interface CalibrationDocument {
  id: string;
  title: string;
  version: string | null;
  lifecycle: string;
  summary: string;
}

type ProductionBackend = Backend & {
  production_ready?: boolean;
  production_gaps?: string[];
};

function backendUsable(backend: Backend): boolean {
  if (backend.output === "TEST_RENDER") return backend.ready;
  return backend.ready && (backend as ProductionBackend).production_ready === true;
}

function backendSuffix(backend: Backend): string {
  if (!backend.ready) return " (not ready)";
  if (backend.output === "TEST_RENDER") return " (workflow diagrams only)";
  const production = backend as ProductionBackend;
  if (!production.production_ready) return " (production preflight blocked)";
  return "";
}

function profileProvider(profile: Profile): string | null {
  const backend = profile.body.backend;
  if (!backend || typeof backend !== "object" || Array.isArray(backend)) return null;
  const provider = (backend as Record<string, unknown>).provider_id;
  return typeof provider === "string" ? provider : null;
}

/**
 * START PRODUCTION CALIBRATION / CHAPTER TEST.
 *
 * The committed calibration document is the source of truth. If the project
 * does not yet have a calibration profile for the selected backend, this
 * creates a small draft profile and then starts the dedicated CALIBRATION run.
 * TEST is allowed here so cast/wardrobe/grounding/readiness can be exercised
 * before ComfyUI exists; its diagram renders are still never artwork.
 */
export function StartCalibration({
  projectId,
  episode,
  documents,
  backends,
  profiles,
}: {
  projectId: string;
  episode: string;
  documents: CalibrationDocument[];
  backends: Backend[];
  profiles: Profile[];
}) {
  const router = useRouter();
  const { busy, error, done, run } = useAction();
  const usable = backends.filter(backendUsable);
  const [documentId, setDocumentId] = useState(documents[0]?.id ?? "");
  const [provider, setProvider] = useState(usable[0]?.provider_id ?? "");
  const selectedBackend = backends.find((b) => b.provider_id === provider) ?? null;

  const start = async () => {
    const created = await run(
      async () => {
        const profileName = `${projectId.slice(0, 55)}-manga-calibration`;
        let profile = [...profiles]
          .filter((p) => p.name === profileName && profileProvider(p) === provider)
          .sort((a, b) => b.version - a.version)[0];

        if (!profile) {
          profile = await vaultFetch<Profile>(`projects/${projectId}/production-profiles`, {
            json: {
              name: profileName,
              body: {
                backend: { provider_id: provider, width: 1024, height: 1456 },
                reference_policy: {
                  per_character: 6,
                  use_candidates: true,
                  use_supplemental: false,
                  stylization: 1,
                },
                character_rules: {},
                grammar: { series: [], pool: 0, limit: 0 },
                setting: { environment_tags: [] },
              },
            },
          });
        }

        return vaultFetch<RunView>(`projects/${projectId}/calibration-runs`, {
          json: {
            episode,
            chapter: 1,
            document_id: documentId,
            profile_id: profile.id,
          },
        });
      },
      "Chapter Test started.",
    );
    if (created) router.push(`/production/runs/${created.id}`);
  };

  if (!documents.length) {
    return (
      <div className="surface panel stack">
        <strong>Chapter Test package not found</strong>
        <p className="hint" style={{ margin: 0 }}>
          Commit a production calibration document first. The launcher never accepts browser-authored calibration text.
        </p>
      </div>
    );
  }

  return (
    <div className="surface panel stack">
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr", alignItems: "end" }}>
        <div className="field compact">
          <label>
            Calibration package
            <select value={documentId} onChange={(e) => setDocumentId(e.target.value)}>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}{d.version ? ` · v${d.version}` : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="field compact">
          <label>
            Page backend
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {backends.map((b) => (
                <option key={b.provider_id} value={b.provider_id} disabled={!backendUsable(b)}>
                  {b.kind.replace("_", " ")} - {b.provider_id}{backendSuffix(b)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <p className="hint" style={{ margin: 0 }}>
        All calibration pages are independent non-canon sampler pages. The run checks the real committed cast,
        character grounding, wardrobe stage, environment inputs and provenance without feeding approved calibration
        pages back into story continuity.
      </p>
      {selectedBackend?.output === "TEST_RENDER" ? (
        <p className="hint" style={{ margin: 0 }}>
          TEST is enough to inspect READY/BLOCKED logic and generate labelled workflow diagrams. It can never count as
          real manga artwork or pass a production sample. Connect ComfyUI later for visual calibration.
        </p>
      ) : null}
      <div className="row">
        <button className="button primary" type="button" disabled={busy || !documentId || !provider} onClick={start}>
          Start Chapter Test
        </button>
        <span className="hint">Opens the committed calibration package as one isolated production run.</span>
      </div>
      <Feedback error={error} done={done} />
    </div>
  );
}

/**
 * START NON-CANON SAMPLE: preview the chapter as the committed sources
 * materialize it, decide where (or whether) each overlay insertion goes for
 * this sample, pick a backend, and start. Placements chosen here are PROPOSED,
 * never confirmed canon.
 */
export function StartSample({
  projectId,
  episode,
  defaultChapter,
  backends,
  defaultOpen = false,
}: {
  projectId: string;
  episode: string;
  defaultChapter: number;
  backends: Backend[];
  defaultOpen?: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(defaultOpen);
  const { busy, error, done, run } = useAction();
  const [chapter, setChapter] = useState(defaultChapter);
  const [placements, setPlacements] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Materialized | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const usable = backends.filter(backendUsable);
  const [provider, setProvider] = useState(usable[0]?.provider_id ?? "fake.deterministic-page");

  const decisions = useCallback(
    () =>
      Object.entries(placements)
        .filter(([, after]) => after !== "")
        .map(([item_key, after]) => ({
          item_key,
          chapter,
          after_base_page: Number(after),
          status: "PROPOSED",
          author: "creator",
          note: "sample placement",
        })),
    [placements, chapter],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPreviewError(null);
    vaultFetch<Materialized>(`projects/${projectId}/episodes/${episode}/materialize`, {
      json: { chapter, decisions: decisions() },
    })
      .then((result) => {
        if (!cancelled) setPreview(result);
      })
      .catch((cause: Error) => {
        if (!cancelled) {
          setPreview(null);
          setPreviewError(cause.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, projectId, episode, chapter, decisions]);

  const basePages = (preview?.body.pages ?? []).filter((p) => p.origin === "base" && p.base_page !== null);
  const insertions = [...(preview?.body.insertions.placed_in_chapter ?? []), ...(preview?.body.insertions.unplaced ?? [])];
  const seen = new Set<string>();
  const uniqueInsertions = insertions.filter((i) => (seen.has(i.item_key) ? false : (seen.add(i.item_key), true)));

  const start = async () => {
    const created = await run(
      () =>
        vaultFetch<RunView>(`projects/${projectId}/episodes/${episode}/sample-runs`, {
          json: { chapter, decisions: decisions(), provider_id: provider },
        }),
      "Sample started.",
    );
    if (created) router.push(`/production/runs/${created.id}`);
  };

  if (!open) {
    return (
      <div className="surface panel spread">
        <span className="hint">Prepare a non-canon chapter sample for {episode}.</span>
        <button className="button small" type="button" onClick={() => setOpen(true)}>
          Prepare sample
        </button>
      </div>
    );
  }

  return (
    <div className="surface panel stack">
      <div className="form-row" style={{ gridTemplateColumns: "140px 1fr", alignItems: "end" }}>
        <div className="field compact">
          <label>
            Chapter
            <input
              type="number"
              min={1}
              value={chapter}
              onChange={(e) => setChapter(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
        </div>
        <div className="field compact">
          <label>
            Page backend
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {backends.map((b) => (
                <option key={b.provider_id} value={b.provider_id} disabled={!backendUsable(b)}>
                  {b.kind.replace("_", " ")} - {b.provider_id}{backendSuffix(b)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {previewError ? <p className="error-text">{previewError}</p> : null}
      {preview ? (
        <div className="stack">
          <p style={{ margin: 0 }}>
            <strong>
              {episode} chapter {chapter}: {preview.body.page_count} integrated provisional pages
            </strong>
            {preview.body.chapter_cut ? (
              <span className="muted">
                {" "}
                · base pages {preview.body.chapter_cut.first_page}-{preview.body.chapter_cut.last_page}
              </span>
            ) : null}
          </p>
          {preview.body.warnings.map((w) => (
            <p key={w} className="hint" style={{ margin: 0 }}>
              {w}
            </p>
          ))}
          {uniqueInsertions.length ? (
            <div className="stack">
              <span className="eyebrow" style={{ margin: 0 }}>
                Overlay insertions - placement for this sample only (proposed, never canon)
              </span>
              {uniqueInsertions.map((item) => (
                <div key={item.item_key} className="form-row" style={{ gridTemplateColumns: "1fr 220px", alignItems: "center" }}>
                  <span style={{ fontSize: 13 }}>
                    <b>{item.item_key}</b>
                    {item.source_beats?.length ? ` · beat ${item.source_beats.map((b) => b.number).join(", ")}` : ""}
                    {item.text ? <span className="muted"> - {item.text.slice(0, 160)}</span> : null}
                    {item.conflict ? <span className="constraint"> · {item.conflict}</span> : null}
                  </span>
                  <select
                    aria-label={`Placement of ${item.item_key}`}
                    value={placements[item.item_key] ?? ""}
                    onChange={(e) => setPlacements({ ...placements, [item.item_key]: e.target.value })}
                  >
                    <option value="">Leave out of this sample</option>
                    {basePages.map((p) => (
                      <option key={p.page_key} value={String(p.base_page)}>
                        After base page {p.base_page}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
            </div>
          ) : null}
          <ol className="muted" style={{ margin: 0, paddingLeft: 22, columns: 2, fontSize: 12.5 }}>
            {preview.body.pages.map((p) => (
              <li key={p.page_key}>
                p. {p.integrated_page ?? "?"} · {p.origin === "overlay" ? "overlay insertion" : `base ${p.base_page}`}
                {p.label ? ` · ${p.label}` : ""}
              </li>
            ))}
          </ol>
        </div>
      ) : !previewError ? (
        <p className="hint">Materializing the chapter from the committed sources…</p>
      ) : null}

      <div className="row">
        <button className="button primary" type="button" disabled={busy || !preview} onClick={start}>
          Start Non-Canon Chapter {chapter} Sample
        </button>
        <span className="hint">Opens a non-canon sample run. Page 1 becomes ready; each next page waits for approval.</span>
      </div>
      <Feedback error={error} done={done} />
    </div>
  );
}

/** START CANONICAL PRODUCTION - shown only once canonical readiness passes. Never automatic. */
export function StartCanonical({ projectId, episode, profileId }: { projectId: string; episode: string; profileId: string }) {
  const router = useRouter();
  const { busy, error, done, run } = useAction();
  const start = async () => {
    if (!window.confirm(`Start canonical ${episode} production from page 1? This is canon.`)) return;
    const created = await run(
      () =>
        vaultFetch<RunView>(`projects/${projectId}/production-runs`, {
          json: { episode, purpose: "PRODUCTION", profile_id: profileId, chapters: [1, 2, 3], decisions: [] },
        }),
      "Canonical production started.",
    );
    if (created) router.push(`/production/runs/${created.id}`);
  };
  return (
    <span className="row">
      <button className="button small primary" type="button" disabled={busy} onClick={start}>
        Start canonical {episode} production
      </button>
      <Feedback error={error} done={done} />
    </span>
  );
}
