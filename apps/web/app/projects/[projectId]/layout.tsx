import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError, type ProjectDetail } from "@/lib/api";
import { ApiDown } from "../../library/acquisition/_components/ui";
import { SubnavLink } from "../../library/acquisition/_components/SubnavLink";
import { SourceLine } from "../_components/EpisodeBoard";
import { ResyncButton } from "../_components/ResyncButton";
import { KIND_LABELS, loadProject } from "../_components/project";

/**
 * Inside a project. The section bar is the project's own: its story, its
 * drafts and approvals, and the production tracks that will hold manga,
 * animation and assets as they are made.
 */
export default async function ProjectLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  let detail: ProjectDetail | null = null;
  let error: string | null = null;
  try {
    detail = await loadProject(projectId);
  } catch (cause) {
    if (cause instanceof ApiUnreachableError) error = cause.message;
    else notFound();
  }
  if (!detail) {
    return (
      <>
        <Link className="crumb" href="/projects" style={{ marginTop: 28 }}>
          ← Projects
        </Link>
        <ApiDown service="Projects" message={error ?? "no response"} />
      </>
    );
  }
  const base = `/projects/${encodeURIComponent(projectId)}`;
  return (
    <>
      <div className="section-bar">
        <div className="section-bar-row">
          <nav className="subnav" aria-label={`${detail.project.title} sections`}>
            <SubnavLink href={base} exact>
              Overview
            </SubnavLink>
            <SubnavLink href={`${base}/story`}>Story</SubnavLink>
            <SubnavLink href={`${base}/ideas`}>Ideas & future beats</SubnavLink>
            <SubnavLink href={`${base}/documents`}>Documents</SubnavLink>
            <SubnavLink href={`${base}/drafts`}>Drafts</SubnavLink>
            <SubnavLink href={`${base}/approved`}>Approved</SubnavLink>
            <SubnavLink href={`${base}/manga`} exact>
              Manga
            </SubnavLink>
            <SubnavLink href={`${base}/manga/production`}>Manga production</SubnavLink>
            <SubnavLink href={`${base}/roughs`}>Roughs (advanced)</SubnavLink>
            <SubnavLink href={`${base}/anime`}>Anime</SubnavLink>
            <SubnavLink href={`${base}/assets`}>Assets</SubnavLink>
            <SubnavLink href={`${base}/extras`}>Extras</SubnavLink>
            <SubnavLink href={`${base}/history`}>History</SubnavLink>
          </nav>
          <div className="freshness">
            <span className="muted">{KIND_LABELS[detail.project.kind] ?? detail.project.kind}</span>
            <b>{detail.project.title}</b>
          </div>
        </div>
        <div className="section-bar-row project-source">
          <SourceLine source={detail.project.source} />
          <ResyncButton projectId={detail.project.id} git={detail.project.source.kind === "git"} />
        </div>
      </div>
      {children}
    </>
  );
}
