import Link from "next/link";
import { ApiUnreachableError, type ProjectSummary, projects } from "@/lib/api";
import { timeAgo } from "@/lib/acquisition";
import { ApiDown, Empty, PageHead } from "../library/acquisition/_components/ui";
import { KIND_LABELS } from "./_components/project";

export const dynamic = "force-dynamic";

/**
 * Every project, as the stories they are. Continuum knows none of them in
 * advance: each is found through its own manifest, and there may be none.
 */
export default async function ProjectsPage() {
  let list: ProjectSummary[] = [];
  let error: string | null = null;
  try {
    list = await projects.list();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  return (
    <>
      <PageHead
        eyebrow="Continuum"
        title="Projects"
        lead="The stories you are making: continuations, alternate endings, what-ifs, crossovers and originals. Each one keeps its own documents, versions and approvals."
      />
      {error ? <ApiDown service="Projects" message={error} /> : null}

      {list.length ? (
        <div className="collection projects">
          {list.map((project) => (
            <Link key={project.id} className="project-card" href={`/projects/${encodeURIComponent(project.id)}`}>
              <p className="eyebrow">{KIND_LABELS[project.kind] ?? project.kind}</p>
              <h2>{project.title}</h2>
              {project.logline ? <p className="logline">{project.logline}</p> : null}
              <div className="project-card-foot">
                <span>
                  <b className="tabular">{project.approved}</b> approved
                </span>
                <span>
                  <b className="tabular">{project.in_progress}</b> in progress
                </span>
                <span className="muted">{timeAgo(project.updated_at)}</span>
              </div>
            </Link>
          ))}
        </div>
      ) : error ? null : (
        <Empty title="No projects yet">
          <p>
            A project appears here when a folder with a <code>continuum.project.json</code> manifest
            is in one of your project sources - the folders named by{" "}
            <code>CONTINUUM_PROJECT_SOURCES</code>, or your projects root.
          </p>
        </Empty>
      )}
    </>
  );
}
