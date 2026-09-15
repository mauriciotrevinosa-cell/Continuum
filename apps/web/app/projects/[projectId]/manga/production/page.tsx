import Link from "next/link";
import { notFound } from "next/navigation";
import { API_BASE, ApiUnreachableError } from "@/lib/api";
import { type Backend, PAGE_STATE_LABEL, type PageState, type Profile, type RunListItem, manga } from "@/lib/manga";
import { ApiDown, Empty } from "../../../../library/acquisition/_components/ui";
import { BackendList, PurposeBadge } from "../../../../production/_parts/manga";
import { loadProject } from "../../../_components/project";
import { StartCanonical, StartSample } from "./StartSample";

export const dynamic = "force-dynamic";

interface Readiness {
  ready: boolean;
  reasons: { kind: string; key?: string; detail?: string }[];
}

async function canonicalReadiness(project: string, episode: string, profile: Profile): Promise<Readiness | null> {
  try {
    const response = await fetch(
      `${API_BASE}/projects/${encodeURIComponent(project)}/episodes/${encodeURIComponent(episode)}/canonical-readiness`,
      {
        method: "POST",
        cache: "no-store",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ profile_id: profile.id, chapters: [1, 2, 3], decisions: [] }),
      },
    );
    return response.ok ? ((await response.json()) as Readiness) : null;
  } catch {
    return null;
  }
}

function RunRow({ run }: { run: RunListItem }) {
  const states = Object.entries(run.states) as [PageState, number][];
  return (
    <Link className="list-item" href={`/production/runs/${run.id}`}>
      <div>
        <h3>
          {run.episode}
          {run.chapter ? ` · chapter ${run.chapter}` : ""} <span className="muted">· {run.pages} pages</span>
        </h3>
        <p className="sub">
          {run.profile ? `${run.profile.name} v${run.profile.version} · ` : ""}
          {states.map(([state, count]) => `${count} ${PAGE_STATE_LABEL[state].toLowerCase()}`).join(" · ")}
          {` · started ${new Date(run.created_at).toLocaleString()}`}
        </p>
      </div>
      <span className="side chips">
        <PurposeBadge purpose={run.purpose} />
        <span className="chip quiet">{run.status.replace("_", " ").toLowerCase()}</span>
      </span>
    </Link>
  );
}

/**
 * Manga production for a project: which artwork backends can draw, the runs
 * already made, and for each episode with an approved panel script the one
 * entry point that matters - START NON-CANON SAMPLE. Canonical production is
 * offered only when a sample has passed and nothing creative blocks it.
 */
export default async function MangaProductionPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const detail = await loadProject(projectId).catch(() => null);
  if (!detail) notFound();
  let runs: RunListItem[] = [];
  let backends: Backend[] = [];
  let profiles: Profile[] = [];
  let error: string | null = null;
  try {
    [runs, backends, profiles] = await Promise.all([
      manga.runs(projectId),
      manga.backends(),
      manga.profiles(projectId),
    ]);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const episodes = detail.episodes.filter((e) =>
    e.documents.some((d) => d.category === "panel-script" && ["APPROVED", "LOCKED"].includes(d.lifecycle)),
  );
  const promoted = profiles.filter((p) => p.status === "PROMOTED").sort((a, b) => b.version - a.version)[0] ?? null;
  const artworkReady = backends.some((b) => b.ready && b.output === "ARTWORK_CANDIDATE");

  return (
    <>
      <header className="page-head" style={{ marginTop: 28 }}>
        <div>
          <p className="eyebrow">Manga · production</p>
          <h1 className="title">Manga production</h1>
          <p className="lead">
            Chapters are drawn page by page from the committed scripts: each page is generated as one composition
            with black-and-white and color finishes, reviewed, and approved before the next page opens. A non-canon
            sample proves the production profile first; canonical production starts only after a sample passes.
          </p>
        </div>
        <Link className="button small ghost" href={`/projects/${projectId}/roughs`}>
          Roughs · advanced / override
        </Link>
      </header>
      {error ? <ApiDown service="manga production" message={error} /> : null}

      <section className="block" aria-label="Artwork backends">
        <div className="block-head">
          <h2>Artwork backends</h2>
        </div>
        {!artworkReady ? (
          <div className="banner">
            <p>
              <strong>No artwork backend is ready.</strong> The test backend proves the workflow with labelled
              diagrams, which can never pass a sample. Connect ComfyUI (local or a remote GPU session) to draw real
              pages.
            </p>
          </div>
        ) : null}
        <BackendList backends={backends} />
      </section>

      {episodes.map((episode) => {
        const episodeRuns = runs.filter((r) => r.episode === episode.code);
        return (
          <section className="block" key={episode.code} aria-label={episode.code}>
            <div className="block-head">
              <h2>
                {episode.code}
                {episode.title ? ` · ${episode.title}` : ""}
                {episode.pages ? <small>{episode.pages} pp.</small> : null}
              </h2>
            </div>
            <div className="stack">
              {episodeRuns.length ? (
                <div className="list">
                  {episodeRuns.map((run) => (
                    <RunRow key={run.id} run={run} />
                  ))}
                </div>
              ) : (
                <p className="hint">No production runs for {episode.code} yet.</p>
              )}
              <StartSample
                projectId={projectId}
                episode={episode.code}
                defaultChapter={episode.code === "S1E1" ? 2 : 1}
                defaultOpen={episode.code === episodes[0]?.code && episodeRuns.length === 0}
                backends={backends}
              />
              <CanonicalStart
                projectId={projectId}
                episode={episode.code}
                promoted={promoted}
                basis={promoted ?? profiles[profiles.length - 1] ?? null}
              />
            </div>
          </section>
        );
      })}
      {!episodes.length && !error ? (
        <Empty title="No episode has an approved panel script">
          <p>Production starts from an approved panel script in the project&apos;s committed documents.</p>
        </Empty>
      ) : null}
    </>
  );
}

async function CanonicalStart({
  projectId,
  episode,
  promoted,
  basis,
}: {
  projectId: string;
  episode: string;
  promoted: Profile | null;
  basis: Profile | null;
}) {
  // Checked against the promoted profile - or, before any SAMPLE PASS, against the
  // latest draft, so creative blockers (checklists, placements) are visible early.
  const readiness = basis ? await canonicalReadiness(projectId, episode, basis) : null;
  const reasons = basis
    ? (readiness?.reasons ?? [{ kind: "UNKNOWN", detail: "readiness could not be checked" }])
    : [{ kind: "SAMPLE_NOT_PASSED", detail: "no production profile has been promoted by a SAMPLE PASS yet" }];
  return (
    <div className="surface panel stack">
      <div className="spread">
        <strong>Start canonical {episode} production</strong>
        {promoted && readiness?.ready ? (
          <StartCanonical projectId={projectId} episode={episode} profileId={promoted.id} />
        ) : (
          <button className="button small" type="button" disabled title="Not available until every reason below is resolved">
            Not available
          </button>
        )}
      </div>
      {reasons.length ? (
        <ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>
          {reasons.map((r, index) => (
            <li key={`${r.kind}-${index}`}>
              <b>{r.kind.replaceAll("_", " ").toLowerCase()}</b>
              {r.key ? ` · ${r.key}` : ""}
              {r.detail ? ` - ${r.detail}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">
          Every creative requirement is met. Canonical production is started deliberately by the creator; it is never
          started automatically.
        </p>
      )}
    </div>
  );
}
