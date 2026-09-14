import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type Readiness, type RoughArtifact, vault, words } from "@/lib/vault";
import { ApiDown, Empty } from "../../../library/acquisition/_components/ui";
import { loadProject } from "../../_components/project";
import { ReadinessBanner, STATE_TONE } from "../../../production/_parts/status";
import { CreateArtifact } from "./CreateArtifact";

export const dynamic = "force-dynamic";


/** Rough pages and panels of this project, each with its attempt history. */
export default async function RoughsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  let artifacts: RoughArtifact[] = [];
  let error: string | null = null;
  let readiness: Readiness | null = null;
  const detail = await loadProject(projectId).catch(() => null);
  if (!detail) notFound();
  try {
    [artifacts, readiness] = await Promise.all([vault.artifacts(projectId), vault.readiness()]);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const scripts = detail.documents
    .filter((d) => !["SUPERSEDED", "ARCHIVED"].includes(d.lifecycle))
    .sort((a, b) => Number(/panel/i.test(b.category + b.title)) - Number(/panel/i.test(a.category + a.title)))
    .map((d) => ({ id: d.id, label: `${d.title}${d.version ? ` v${d.version}` : ""} · ${words(d.lifecycle)}` }));

  return (
    <>
      <header className="page-head" style={{ marginTop: 28 }}>
        <div>
          <p className="eyebrow">Manga · rough production</p>
          <h1 className="title">Roughs</h1>
          <p className="lead">
            A page or panel from the panel script, drafted from a reference bundle - new, edited from a
            source plate, composited, or laid out - then reviewed, regenerated or approved. Every
            attempt is kept.
          </p>
        </div>
      </header>
      {error ? <ApiDown service="production" message={error} /> : null}
      <ReadinessBanner readiness={readiness} />

      {artifacts.length ? (
        <div className="list" style={{ marginBottom: 28 }}>
          {artifacts.map((artifact) => {
            const latest = artifact.attempts[0];
            return (
              <Link className="list-item" key={artifact.id} href={`/production/roughs/${artifact.id}`}>
                <div>
                  <h3>
                    {artifact.episode} · page {artifact.page}
                    {artifact.panel ? ` · panel ${artifact.panel}` : ""}
                    {artifact.title ? <span className="muted"> · {artifact.title}</span> : null}
                  </h3>
                  <p className="sub">
                    {artifact.attempts.length} attempt{artifact.attempts.length === 1 ? "" : "s"}
                    {artifact.panel_script.document
                      ? ` · ${artifact.panel_script.document} v${artifact.panel_script.version ?? "?"}`
                      : ""}
                  </p>
                </div>
                <span className="side">
                  {artifact.approved_attempt_id ? (
                    <span className="chip ok">Approved</span>
                  ) : latest ? (
                    <span className={`chip ${STATE_TONE[latest.display_state] ?? "muted"}`}>
                      {words(latest.display_state)}
                    </span>
                  ) : (
                    <span className="chip muted">No attempts</span>
                  )}
                </span>
              </Link>
            );
          })}
        </div>
      ) : error ? null : (
        <div style={{ marginBottom: 28 }}>
          <Empty title="No roughs yet">
            <p>Pick a page from the panel script to start - a small slice first, not the whole chapter.</p>
          </Empty>
        </div>
      )}
      <CreateArtifact projectId={projectId} scripts={scripts} />
    </>
  );
}
