import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type ChapterView, manga, vaultImage } from "@/lib/manga";
import { VaultNotFound, words } from "@/lib/vault";
import { ApiDown } from "../../../../library/acquisition/_components/ui";
import { PageStateChip, PurposeBadge } from "../../../_parts/manga";
import { ChapterActions } from "./ChapterActions";

export const dynamic = "force-dynamic";

const QA_LABEL: Record<string, string> = {
  pages: "Pages planned",
  rendered: "Pages test-rendered",
  pages_with_warnings: "Pages with warnings",
  pages_with_cast_warnings: "Cast warnings",
  pages_with_character_warnings: "Character-reference warnings",
  pages_with_environment_gaps: "Environment gaps",
  pages_with_grammar: "Pages with grammar pages",
};

/**
 * The chapter as a sequence: every page's plan, the references chosen for it,
 * its test render and the QA warnings - page 1, page 2, page 3 - so reference
 * decisions can be criticised before any GPU renders art.
 */
export default async function ChapterReviewPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (!/^[0-9a-f-]{36}$/.test(runId)) notFound();
  let view: ChapterView | null = null;
  let error: string | null = null;
  try {
    view = await manga.chapter(runId);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!view) return <ApiDown service="manga production" message={error ?? "no response"} />;
  const { run, pages, qa } = view;
  const preview = run.purpose === "WORKFLOW_TEST";
  const pending = pages.filter((p) => p.render.state === "QUEUED").length;

  return (
    <>
      <Link className="crumb" href={`/production/runs/${run.id}`}>
        ← {run.episode}
        {run.chapter ? ` chapter ${run.chapter}` : ""} run
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">
            {run.project_key} · {run.episode}
            {run.chapter ? ` · chapter ${run.chapter}` : ""} · {run.profile ? `${run.profile.name} v${run.profile.version}` : ""}
          </p>
          <h1 className="title">Chapter review</h1>
          <p className="row" style={{ gap: 8, margin: "6px 0" }}>
            <PurposeBadge purpose={run.purpose} />
            {preview ? <span className="test-banner">Workflow test - not artwork</span> : null}
          </p>
          <p className="lead">
            Every page in order: who appears, what it is about, which references were chosen and why, its test render,
            and what looks wrong. Warnings flag problems; nothing here is fixed or rewritten automatically.
          </p>
        </div>
        <ChapterActions runId={run.id} preview={preview} pending={pending} />
      </header>

      <section className="block" aria-label="Chapter QA">
        <div className="block-head">
          <h2>QA summary</h2>
        </div>
        <div className="stat-grid">
          {Object.entries(QA_LABEL).map(([key, label]) => (
            <div key={key} className="stat">
              <span className="n">{String(qa[key as keyof typeof qa])}</span>
              <span className="l">{label}</span>
            </div>
          ))}
        </div>
        {Object.keys(qa.counts).length ? (
          <p className="hint" style={{ marginTop: 10 }}>
            {Object.entries(qa.counts)
              .sort((a, b) => b[1] - a[1])
              .map(([kind, count]) => `${words(kind)} ×${count}`)
              .join(" · ")}
          </p>
        ) : null}
        {qa.overused_references.length ? (
          <ul className="warn-list">
            {qa.overused_references.map((r) => (
              <li key={r.reference} className="warn">
                Used on {r.pages} pages: {r.reference}
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      <section className="block" aria-label="Pages">
        <div className="block-head">
          <h2>
            Pages <small>{pages.length}</small>
          </h2>
        </div>
        <div className="chapter-grid">
          {pages.map((p) => {
            const image = p.render.attempt_id
              ? vaultImage(`/production/attempts/${p.render.attempt_id}/image?kind=COMPOSITION_MASTER`)
              : null;
            const serious = p.warnings.filter((w) => w.severity !== "info");
            return (
              <Link key={p.id} className="chapter-page" href={`/production/runs/${run.id}/pages/${p.id}`}>
                <div className="sheet-thumb">
                  {image ? (
                    // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
                    <img src={image} alt={`Page ${p.sequence} test render`} loading="lazy" />
                  ) : (
                    <span>{p.render.state === "QUEUED" ? "rendering…" : "not rendered"}</span>
                  )}
                </div>
                <div className="stack" style={{ gap: 5, minWidth: 0 }}>
                  <div className="spread">
                    <b>
                      {p.sequence}
                      {p.integrated_page ? <span className="muted"> · p.{p.integrated_page}</span> : null}
                    </b>
                    <PageStateChip state={p.state} />
                  </div>
                  <span className="muted" style={{ fontSize: 11.5 }}>
                    {p.origin === "overlay" ? `overlay ${p.lineage.insertion ?? ""}` : `base ${p.base_page ?? "?"}`}
                    {p.scene ? ` · ${p.scene}` : ""}
                  </span>
                  <span style={{ fontSize: 12 }}>
                    <b>{p.plan.primary_character ?? "nobody"}</b>
                    {p.plan.supporting_characters.length ? ` + ${p.plan.supporting_characters.join(", ")}` : ""} ·{" "}
                    {p.plan.primary_intent ? words(p.plan.primary_intent) : "no intent"}
                    {p.plan.silent ? " · silent" : ` · ${p.plan.dialogue_lines} line(s)`}
                  </span>
                  <div className="mini-thumbs" title="Character references">
                    {p.characters.flatMap((c) =>
                      c.observations.slice(0, 2).map((o) => (
                        // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
                        <img
                          key={`${c.name}-${o.id}`}
                          src={vaultImage(o.image)}
                          alt={`${c.name} ${o.status}`}
                          title={`${c.name} · ${o.authority} · ${o.status}`}
                          style={o.status === "CANDIDATE" ? { opacity: 0.55 } : undefined}
                        />
                      )),
                    )}
                  </div>
                  <div className="mini-thumbs" title="Grammar and technique pages">
                    {[...p.grammar.slice(0, 3), ...p.technique.slice(0, 2)].map((g) =>
                      g.image ? (
                        // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
                        <img key={`${g.role}-${g.locator}`} src={vaultImage(g.image)} alt={g.role} title={`${g.role} · ${g.label}`} />
                      ) : null,
                    )}
                  </div>
                  <span className="muted" style={{ fontSize: 11.5 }}>
                    grammar {p.grammar.length} · technique {p.technique.length} · environment{" "}
                    {p.environment.length ? `${p.environment.length} tagged` : p.environment_pages.length ? `${p.environment_pages.length} unverified` : "none"}
                    {p.continuity_pages ? ` · continuity ${p.continuity_pages}` : ""}
                  </span>
                  {serious.length ? (
                    <ul className="warn-list">
                      {serious.slice(0, 4).map((w, index) => (
                        <li key={`${w.kind}-${index}`} className={w.severity}>
                          {w.detail}
                        </li>
                      ))}
                      {serious.length > 4 ? <li className="info">+{serious.length - 4} more</li> : null}
                    </ul>
                  ) : (
                    <span className="hint" style={{ fontSize: 11.5 }}>
                      No warnings
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </>
  );
}
