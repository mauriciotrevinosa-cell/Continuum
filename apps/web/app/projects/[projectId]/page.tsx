import Link from "next/link";
import type { PipelineStage, ProjectDocument } from "@/lib/api";
import {
  DocumentRow,
  HISTORY,
  KIND_LABELS,
  LifecycleChip,
  isContinuity,
  isDraft,
  isExtra,
  loadProject,
} from "../_components/project";

export const dynamic = "force-dynamic";

const TRACKS: { key: string; label: string }[] = [
  { key: "story", label: "Story" },
  { key: "manga", label: "Manga" },
  { key: "anime", label: "Anime" },
];

function episodes(documents: ProjectDocument[]): [string, ProjectDocument[]][] {
  const map = new Map<string, ProjectDocument[]>();
  for (const d of documents) {
    if (!d.episode || HISTORY.includes(d.lifecycle)) continue;
    map.set(d.episode, [...(map.get(d.episode) ?? []), d]);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }));
}

function Track({ stages, label, projectHref }: { stages: PipelineStage[]; label: string; projectHref: string }) {
  if (!stages.length) return null;
  const target = label === "Manga" ? "manga" : label === "Anime" ? "anime" : "story";
  return (
    <div className="track">
      <Link className="track-label" href={`${projectHref}/${target}`}>
        {label}
      </Link>
      <ol className="stages">
        {stages.map((stage) => (
          <li key={stage.id} className={stage.artifacts ? "has" : undefined} title={stage.description}>
            <span className="stage-title">{stage.title}</span>
            <span className="stage-count tabular">{stage.artifacts || "—"}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** A project's home: what is decided, what is being written, and where it is going. */
export default async function ProjectHome({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const detail = await loadProject(projectId);
  const { project, documents, pipeline } = detail;
  const href = `/projects/${encodeURIComponent(project.id)}`;
  const continuity = documents.filter(isContinuity);
  const progress = documents.filter(isDraft);
  const extras = documents.filter(isExtra);
  const unfiled = documents.filter((d) => !d.filed);
  const eps = episodes(documents);

  return (
    <>
      <header className="project-hero">
        <p className="eyebrow">{KIND_LABELS[project.kind] ?? project.kind}</p>
        <h1 className="title xl">{project.title}</h1>
        {project.logline ? <p className="logline big">{project.logline}</p> : null}
        {detail.description ? <p className="lead">{detail.description}</p> : null}
      </header>

      <div className="project-split">
        <section aria-labelledby="continuity">
          <div className="block-head">
            <h2 id="continuity">
              Approved continuity<small>{continuity.length}</small>
            </h2>
            <Link className="more" href={`${href}/approved`}>
              All approved →
            </Link>
          </div>
          {continuity.length ? (
            <div className="list">
              {continuity.slice(0, 6).map((d) => (
                <DocumentRow key={d.id} projectId={project.id} document={d} />
              ))}
            </div>
          ) : (
            <div className="empty">
              <h3>Nothing approved yet</h3>
              <p>Documents become continuity only when they are explicitly approved.</p>
            </div>
          )}
        </section>

        <section aria-labelledby="progress">
          <div className="block-head">
            <h2 id="progress">
              In progress<small>{progress.length}</small>
            </h2>
            <Link className="more" href={`${href}/drafts`}>
              All drafts →
            </Link>
          </div>
          {progress.length ? (
            <div className="list">
              {progress.slice(0, 6).map((d) => (
                <DocumentRow key={d.id} projectId={project.id} document={d} />
              ))}
            </div>
          ) : (
            <div className="empty">
              <h3>No work in progress</h3>
              <p>Ideas, drafts and documents in review appear here.</p>
            </div>
          )}
          {extras.length ? (
            <p className="muted" style={{ margin: "14px 0 0", fontSize: 13 }}>
              <Link href={`${href}/extras`}>
                {extras.length} extra{extras.length === 1 ? "" : "s"}
              </Link>{" "}
              kept alongside the story - notes and experiments, not canon.
            </p>
          ) : null}
          {unfiled.length ? (
            <p className="muted" style={{ margin: "6px 0 0", fontSize: 13 }}>
              {unfiled.length} document{unfiled.length === 1 ? " is" : "s are"} in the project folder
              but not registered in its manifest, so {unfiled.length === 1 ? "it has" : "they have"} no
              standing yet.
            </p>
          ) : null}
        </section>
      </div>

      {eps.length ? (
        <section className="block" aria-labelledby="episodes">
          <div className="block-head">
            <h2 id="episodes">Episodes</h2>
          </div>
          <div className="episodes">
            {eps.map(([episode, docs]) => (
              <div className="episode" key={episode}>
                <span className="episode-code">{episode}</span>
                <div className="episode-docs">
                  {docs.map((d) => (
                    <Link
                      key={d.id}
                      href={`${href}/documents/${encodeURIComponent(d.id)}`}
                      className="episode-doc"
                    >
                      <span>{d.title}</span>
                      <LifecycleChip lifecycle={d.lifecycle} />
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {pipeline.length ? (
        <section className="block" aria-labelledby="production">
          <div className="block-head">
            <h2 id="production">
              Production<small>how an episode becomes manga, then animation</small>
            </h2>
          </div>
          <div className="surface tracks">
            {TRACKS.map((track) => (
              <Track
                key={track.key}
                label={track.label}
                projectHref={href}
                stages={pipeline.filter((s) => s.track === track.key)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {project.warnings.length ? (
        <details className="disclosure block">
          <summary>{project.warnings.length} note(s) about this project&apos;s manifest</summary>
          <div className="disclosure-body">
            {project.warnings.map((w) => (
              <p key={w} style={{ margin: "0 0 4px" }}>
                {w}
              </p>
            ))}
          </div>
        </details>
      ) : null}
    </>
  );
}
