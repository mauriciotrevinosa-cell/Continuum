import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError, type ProjectDocumentBody, projects } from "@/lib/api";
import { formatWhen } from "@/lib/acquisition";
import { ApiDown } from "../../../../library/acquisition/_components/ui";
import { InlineText, Markdown, documentFields, parseMarkdown, plainText } from "../../../_components/Markdown";
import { CONTINUITY, LIFECYCLE_LABELS, LifecycleChip, StandingChips } from "../../../_components/project";

export const dynamic = "force-dynamic";

/**
 * A project document, read as a document - not as a file. The source is
 * one click away for anyone who wants it.
 */
export default async function ProjectDocumentPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
}) {
  const { projectId, documentId } = await params;
  let body: ProjectDocumentBody | null = null;
  let error: string | null = null;
  try {
    body = await projects.document(projectId, documentId);
  } catch (cause) {
    if (cause instanceof ApiUnreachableError) error = cause.message;
    else notFound();
  }
  if (!body) return <ApiDown service="Projects" message={error ?? "no response"} />;

  const { document, markdown, versions } = body;
  const { headings } = parseMarkdown(markdown);
  const fields = documentFields(markdown);
  const outline = headings.filter((h) => h.depth === 2 || h.depth === 3);
  const base = `/projects/${encodeURIComponent(projectId)}`;
  const approved = CONTINUITY.includes(document.lifecycle);

  return (
    <div className="doc-layout">
      <article className="doc">
        <Link className="crumb" href={`${base}/documents`}>
          ← {body.project.title}
        </Link>
        <header className="doc-head">
          <p className="eyebrow">
            {[document.episode, document.category, document.version ? `version ${document.version}` : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <h1 className="title">{document.title}</h1>
          <div className="chips" style={{ marginTop: 14 }}>
            <LifecycleChip lifecycle={document.lifecycle} />
            <StandingChips document={document} />
            {document.superseded_by ? (
              <Link className="chip quiet" href={`${base}/documents/${encodeURIComponent(document.superseded_by)}`}>
                Superseded — read the newer version
              </Link>
            ) : null}
            {!document.filed ? <span className="chip quiet">Not registered in the project</span> : null}
          </div>
          {!approved ? (
            <p className="doc-note">
              {LIFECYCLE_LABELS[document.lifecycle]}: this is not approved continuity.
            </p>
          ) : null}
          {document.overridden_by.map((o) => (
            <p key={o.document} className="doc-note">
              Overridden in part by{" "}
              <Link href={`${base}/documents/${encodeURIComponent(o.document)}`}>{o.document}</Link>: {o.scope}
            </p>
          ))}
          {document.overrides.map((o) => (
            <p key={o.document} className="doc-note">
              This document overrides part of{" "}
              <Link href={`${base}/documents/${encodeURIComponent(o.document)}`}>{o.document}</Link>: {o.scope}
            </p>
          ))}
          {fields.length ? (
            <dl className="doc-fields" aria-label="The author's notes">
              {fields.map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>
                    <InlineText text={value} />
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </header>

        <Markdown source={markdown} asDocument />

        <details className="disclosure block">
          <summary>View source</summary>
          <div className="disclosure-body">
            <pre className="source">
              <code>{markdown}</code>
            </pre>
          </div>
        </details>
      </article>

      <aside className="doc-aside">
        {outline.length ? (
          <nav aria-label="Outline">
            <h2>Contents</h2>
            <ol>
              {outline.map((h) => (
                <li key={h.id} className={h.depth === 3 ? "outline-sub" : undefined}>
                  <a href={`#${h.id}`}>{plainText(h.text)}</a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
        {versions.length > 1 ? (
          <nav aria-label="Versions">
            <h2>Versions</h2>
            <ol>
              {versions.map((v) => (
                <li key={v.id}>
                  <Link
                    href={`${base}/documents/${encodeURIComponent(v.id)}`}
                    aria-current={v.id === document.id ? "page" : undefined}
                  >
                    v{v.version ?? "?"} · {LIFECYCLE_LABELS[v.lifecycle]}
                  </Link>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
        {document.constraints.length ? (
          <nav aria-label="Constraints">
            <h2>Keep when revising</h2>
            <ul>
              {document.constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </nav>
        ) : null}
        <p className="muted" style={{ fontSize: 12 }}>
          Changed {formatWhen(document.modified_at)}
        </p>
      </aside>
    </div>
  );
}
