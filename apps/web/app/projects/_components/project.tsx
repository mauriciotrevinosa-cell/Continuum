/**
 * Shared pieces of the project workspace.
 *
 * Nothing here knows any project. Sections, lifecycle words and the document
 * row are vocabulary; which documents appear where is decided by the data the
 * API returns - the project's own manifest.
 */
import Link from "next/link";
import { cache } from "react";
import { type DocumentLifecycle, type ProjectDocument, projects } from "@/lib/api";
import { timeAgo } from "@/lib/acquisition";

/** One request, one fetch: the layout and the page share this result. */
export const loadProject = cache((id: string) => projects.detail(id));

export const LIFECYCLE_LABELS: Record<DocumentLifecycle, string> = {
  IDEA: "Idea",
  DRAFT: "Draft",
  REVIEW: "In review",
  APPROVED: "Approved",
  LOCKED: "Locked",
  SUPERSEDED: "Superseded",
  ARCHIVED: "Archived",
  UNFILED: "Unfiled",
};

const LIFECYCLE_TONES: Record<DocumentLifecycle, string> = {
  IDEA: "muted",
  DRAFT: "info",
  REVIEW: "warn",
  APPROVED: "ok",
  LOCKED: "accent",
  SUPERSEDED: "muted",
  ARCHIVED: "muted",
  UNFILED: "muted",
};

export const CONTINUITY: DocumentLifecycle[] = ["APPROVED", "LOCKED"];
export const IN_PROGRESS: DocumentLifecycle[] = ["IDEA", "DRAFT", "REVIEW", "UNFILED"];
export const HISTORY: DocumentLifecycle[] = ["SUPERSEDED", "ARCHIVED"];

/** Sections whose documents are kept alongside the story, never as part of it. */
export const EXTRA_SECTIONS = ["extra", "reference"];

/** Approved or locked: the authoritative record. */
export const isContinuity = (d: ProjectDocument) => CONTINUITY.includes(d.lifecycle);

/** Unapproved work on the story or its production - not extras, not history. */
export const isDraft = (d: ProjectDocument) =>
  IN_PROGRESS.includes(d.lifecycle) && !EXTRA_SECTIONS.includes(d.section) && !d.resolved_by;

/** Kept material that is not canon: notes, references, experiments. */
export const isExtra = (d: ProjectDocument) =>
  EXTRA_SECTIONS.includes(d.section) && !HISTORY.includes(d.lifecycle);

export const KIND_LABELS: Record<string, string> = {
  original: "Original story",
  continuation: "Continuation",
  "alternate-ending": "Alternate ending",
  "what-if": "What if",
  crossover: "Crossover",
  other: "Project",
};

export interface Section {
  key: string;
  label: string;
  description: string;
  select: (d: ProjectDocument) => boolean;
}

/**
 * The workspace's parts. Story, Drafts, Approved and Extras are views over
 * documents; Manga, Anime and Assets hold production artifacts, which
 * arrive with the production phases.
 */
export const SECTIONS: Section[] = [
  {
    key: "story",
    label: "Story",
    description: "The story itself: spine, arcs and episodes, current versions.",
    select: (d) => d.section === "story" && !HISTORY.includes(d.lifecycle),
  },
  {
    key: "drafts",
    label: "Drafts",
    description:
      "Work in progress on the story and its production: ideas, drafts and documents in review. Not continuity until approved.",
    select: isDraft,
  },
  {
    key: "approved",
    label: "Approved",
    description: "The authoritative record. A document is here only because it was approved.",
    select: isContinuity,
  },
  {
    key: "documents",
    label: "Documents",
    description: "Every document of the project, whatever its standing.",
    select: () => true,
  },
  {
    key: "extras",
    label: "Extras",
    description:
      "Notes, references and experiments kept with the project. Useful, preserved, and not canon.",
    select: isExtra,
  },
  {
    key: "history",
    label: "History",
    description:
      "Every version of every document, oldest to newest. A revision is a new version; nothing is overwritten.",
    select: (d) => Boolean(d.lineage),
  },
];

export function LifecycleChip({ lifecycle }: { lifecycle: DocumentLifecycle }) {
  return <span className={`chip ${LIFECYCLE_TONES[lifecycle]}`}>{LIFECYCLE_LABELS[lifecycle]}</span>;
}

const MATURITY_LABELS: Record<string, string> = {
  ROUGH: "Rough",
  DETAILED: "Detailed",
  PRODUCTION_READY: "Production-ready",
};
const AUTHORITY_LABELS: Record<string, string> = {
  RULE: "Authoritative rule",
  CORRECTION: "Authoritative correction",
  INDEX: "Source-of-truth index",
};

/** Maturity and authority beside the lifecycle: an approved rough roadmap is not a panel script. */
export function StandingChips({ document }: { document: ProjectDocument }) {
  return (
    <>
      {document.maturity ? (
        <span className={`chip plain ${document.maturity === "PRODUCTION_READY" ? "ok" : "muted"}`}>
          {MATURITY_LABELS[document.maturity]}
        </span>
      ) : null}
      {AUTHORITY_LABELS[document.authority] ? (
        <span className="chip plain accent">{AUTHORITY_LABELS[document.authority]}</span>
      ) : null}
      {document.overridden_by.length ? (
        <span className="chip plain warn" title={document.overridden_by.map((o) => `${o.document}: ${o.scope}`).join("; ")}>
          Partly overridden
        </span>
      ) : null}
    </>
  );
}

export function DocumentRow({ projectId, document }: { projectId: string; document: ProjectDocument }) {
  const meta = [
    document.episode,
    document.category !== "document" ? document.category : null,
    document.version ? `v${document.version}` : null,
    document.dated ?? (document.modified_at ? `changed ${timeAgo(document.modified_at)}` : null),
  ].filter(Boolean);
  return (
    <Link
      className="list-item doc-row"
      href={`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(document.id)}`}
    >
      <div style={{ minWidth: 0 }}>
        <h3 className={HISTORY.includes(document.lifecycle) ? "historic" : undefined}>{document.title}</h3>
        {document.summary ? <p className="sub">{document.summary}</p> : null}
        <p className="sub doc-meta">{meta.join(" · ")}</p>
      </div>
      <div className="side chips">
        <StandingChips document={document} />
        <LifecycleChip lifecycle={document.lifecycle} />
      </div>
    </Link>
  );
}
