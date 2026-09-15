import Link from "next/link";
import { notFound } from "next/navigation";
import type { PipelineStage, ProjectDocument } from "@/lib/api";
import { DocumentRow, LifecycleChip, SECTIONS, loadProject } from "../../_components/project";

export const dynamic = "force-dynamic";

const PRODUCTION: Record<
  string,
  { title: string; lead: string; empty: string; holds: string[]; documents: boolean }
> = {
  manga: {
    title: "Manga",
    empty: "No manga scripts or pages yet",
    documents: true,
    lead: "Panel scripts, rough pages, final pages and approved chapters. The manga is a real artifact of the project, not scaffolding.",
    holds: ["Panel scripts", "Rough pages and corrections", "Final pages", "Approved, locked chapters"],
  },
  anime: {
    title: "Anime",
    empty: "No anime adaptation work yet",
    documents: true,
    lead: "Episode → adaptation draft → animatic → shots. Every shot stays inspectable: nothing arrives as a finished file to be taken on trust.",
    holds: [
      "Adaptation drafts from approved chapters",
      "Animatics and timing",
      "Shots: purpose, source scene or panel, duration, characters, location, dialogue and audio, camera and composition",
      "Each shot's animation tier (S, A, B, C or D), status and dependencies",
      "Generated attempts, and the one that was approved",
    ],
  },
  assets: {
    title: "Assets",
    empty: "No assets yet",
    documents: false,
    lead: "Reference sheets, backgrounds, character and prop designs, audio - the reusable pieces production draws on.",
    holds: ["Character and prop sheets", "Backgrounds and locations", "Audio and music", "Reference material"],
  },
};

function History({ projectId, documents }: { projectId: string; documents: ProjectDocument[] }) {
  const lineages = new Map<string, ProjectDocument[]>();
  for (const d of documents) {
    if (!d.lineage) continue;
    lineages.set(d.lineage, [...(lineages.get(d.lineage) ?? []), d]);
  }
  const byTitle = (a: [string, ProjectDocument[]], b: [string, ProjectDocument[]]) =>
    a[1][0].title.localeCompare(b[1][0].title);
  const revised = [...lineages.entries()].filter(([, v]) => v.length > 1).sort(byTitle);
  const single = [...lineages.entries()].filter(([, v]) => v.length === 1).sort(byTitle);
  return (
    <>
      {revised.length ? (
        <Lineages projectId={projectId} lineages={revised} />
      ) : (
        <div className="empty">
          <h3>No document has been revised yet</h3>
          <p>When a document is redone, its new version appears here with the ones before it.</p>
        </div>
      )}
      {single.length ? (
        <section className="block" aria-labelledby="single">
          <div className="block-head">
            <h2 id="single">
              One version so far<small>{single.length}</small>
            </h2>
          </div>
          <div className="list">
            {single.map(([lineage, [d]]) => (
              <Link
                key={lineage}
                className="list-item single-version"
                href={`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(d.id)}`}
              >
                <h3>{d.title}</h3>
                <div className="side">
                  <span className="muted tabular">v{d.version ?? "?"}</span>
                  <LifecycleChip lifecycle={d.lifecycle} />
                </div>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

function Lineages({ projectId, lineages }: { projectId: string; lineages: [string, ProjectDocument[]][] }) {
  return (
    <div className="lineages">
      {lineages.map(([lineage, versions]) => {
        const ordered = [...versions].sort((a, b) =>
          (a.version ?? "0").localeCompare(b.version ?? "0", undefined, { numeric: true }),
        );
        return (
          <section className="lineage" key={lineage}>
            <h3>{ordered[ordered.length - 1].title}</h3>
            <ol>
              {ordered.map((d) => (
                <li key={d.id}>
                  <Link href={`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(d.id)}`}>
                    <span className="version tabular">v{d.version ?? "?"}</span>
                    <LifecycleChip lifecycle={d.lifecycle} />
                    {d.superseded_by ? (
                      <span className="muted">
                        replaced by v{ordered.find((o) => o.id === d.superseded_by)?.version ?? "?"}
                      </span>
                    ) : null}
                    {d.derived_from ? <span className="muted">derived from {d.derived_from}</span> : null}
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        );
      })}
    </div>
  );
}

function Production({
  section,
  stages,
  documents,
  projectId,
}: {
  section: string;
  stages: PipelineStage[];
  documents: ProjectDocument[];
  projectId: string;
}) {
  const info = PRODUCTION[section];
  const related = info.documents ? documents.filter((d) => d.section === "production") : [];
  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Production</p>
          <h1 className="title">{info.title}</h1>
          <p className="lead">{info.lead}</p>
        </div>
        {section === "manga" ? (
          <Link className="button primary" href={`/projects/${encodeURIComponent(projectId)}/manga/production`}>
            Open manga production
          </Link>
        ) : null}
      </header>
      {section === "manga" ? (
        <div className="banner">
          <p>
            <strong>Manga production is page by page.</strong> Start a non-canon chapter sample, review each page with
            its master, black-and-white and color finishes, and approve before the next page opens.{" "}
            <Link href={`/projects/${encodeURIComponent(projectId)}/manga/production`}>Go to manga production</Link>
          </p>
        </div>
      ) : null}
      {stages.length ? (
        <section aria-labelledby="stages">
          <div className="block-head">
            <h2 id="stages">Stages</h2>
          </div>
          <div className="list">
            {stages.map((stage) => (
              <div className="list-item" key={stage.id}>
                <div>
                  <h3>{stage.title}</h3>
                  <p className="sub">{stage.description}</p>
                </div>
                <div className="side">
                  <span className="muted tabular">
                    {stage.artifacts ? `${stage.artifacts} artifact(s)` : "nothing yet"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <section className="block empty" style={{ textAlign: "left" }}>
        <h3>{info.empty}</h3>
        <p style={{ margin: "0 0 10px" }}>
          This part of the workspace fills as production begins. It will hold:
        </p>
        <ul className="holds">
          {info.holds.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      </section>
      {related.length ? (
        <section className="block" aria-labelledby="related">
          <div className="block-head">
            <h2 id="related">Production documents</h2>
          </div>
          <div className="list">
            {related.map((d) => (
              <DocumentRow key={d.id} projectId={projectId} document={d} />
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

export default async function ProjectSection({
  params,
}: {
  params: Promise<{ projectId: string; section: string }>;
}) {
  const { projectId, section } = await params;
  const detail = await loadProject(projectId);

  if (section in PRODUCTION) {
    const stages = detail.pipeline.filter((s) => s.track === section);
    return <Production section={section} stages={stages} documents={detail.documents} projectId={projectId} />;
  }

  const view = SECTIONS.find((s) => s.key === section);
  if (!view) notFound();
  const selected = detail.documents.filter(view.select);

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">{detail.project.title}</p>
          <h1 className="title">{view.label}</h1>
          <p className="lead">{view.description}</p>
        </div>
      </header>
      {section === "history" ? (
        selected.length ? (
          <History projectId={projectId} documents={selected} />
        ) : (
          <div className="empty">
            <h3>No versioned documents yet</h3>
          </div>
        )
      ) : selected.length ? (
        <div className="list">
          {selected.map((d) => (
            <DocumentRow key={d.id} projectId={projectId} document={d} />
          ))}
        </div>
      ) : (
        <div className="empty">
          <h3>Nothing here yet</h3>
          <p>
            {section === "approved"
              ? "A document appears here only after it is explicitly approved."
              : "Documents appear here as the project grows."}
          </p>
        </div>
      )}
    </>
  );
}
