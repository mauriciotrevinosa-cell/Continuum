import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type RunView, manga, pageBlocker, vaultImage } from "@/lib/manga";
import { VaultNotFound } from "@/lib/vault";
import { ApiDown } from "../../../library/acquisition/_components/ui";
import { PageStateChip, PurposeBadge, Reasons } from "../../_parts/manga";
import { RunActions } from "./RunActions";

export const dynamic = "force-dynamic";

function runLabel(purpose: string): string {
  if (purpose === "PRODUCTION") return "production";
  if (purpose === "CALIBRATION") return "Chapter Test";
  return "sample";
}

/**
 * One production run: what it is (calibration, a non-canon sample or canonical
 * production), which profile and continuity version it is on, the current and
 * next page, and a contact sheet of every page with its state.
 */
export default async function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  if (!/^[0-9a-f-]{36}$/.test(runId)) notFound();
  let run: RunView | null = null;
  let error: string | null = null;
  try {
    run = await manga.run(runId);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!run) return <ApiDown service="manga production" message={error ?? "no response"} />;
  const current = run.pages.find((p) => p.id === run.next_page_id) ?? null;
  const next = current ? run.pages.find((p) => p.sequence === current.sequence + 1) ?? null : null;
  const approved = run.pages.filter((p) => p.state === "APPROVED").length;
  const stale = run.pages.filter((p) => p.state === "STALE");
  const base = `/production/runs/${run.id}`;

  return (
    <>
      <Link className="crumb" href={`/projects/${run.project_key}/manga/production`}>
        ← Manga production
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">
            {run.project_key} · {run.episode}
            {run.chapter ? ` · chapter ${run.chapter}` : ""}
          </p>
          <h1 className="title">
            {run.episode}
            {run.chapter ? ` chapter ${run.chapter}` : ""} {runLabel(run.purpose)}
          </h1>
          <p className="row" style={{ gap: 8, margin: "6px 0" }}>
            <PurposeBadge purpose={run.purpose} />
            <span className="chip quiet">{run.status.replace("_", " ").toLowerCase()}</span>
          </p>
          <div className="run-facts">
            <span>
              Profile <b>{run.profile.name}</b> v{run.profile.version} · {run.profile.status.toLowerCase()}
            </span>
            <span>
              Continuity <b>v{run.continuity.version}</b> · {run.continuity.reason}
            </span>
            <span>
              <b>{approved}</b> of {run.pages.length} pages approved
            </span>
          </div>
        </div>
      </header>

      <div className="row" style={{ marginBottom: 8 }}>
        <Link className="button small primary" href={`${base}/chapter`}>
          Chapter review - all {run.pages.length} pages
        </Link>
      </div>

      <section className="block" aria-label="Current page">
        <div className="block-head">
          <h2>Current page</h2>
        </div>
        {current ? (
          <div className="surface panel stack">
            <div className="spread">
              <div className="stack" style={{ gap: 2 }}>
                <strong>
                  Page {current.sequence}
                  {current.integrated_page ? ` · p. ${current.integrated_page}` : ""}
                  {current.label ? ` · ${current.label}` : ""}
                </strong>
                <span className="muted mono">{current.page_key}</span>
              </div>
              <span className="row">
                <PageStateChip state={current.state} />
                <Link className="button small primary" href={`${base}/pages/${current.id}`}>
                  Open page {current.sequence}
                </Link>
              </span>
            </div>
            {pageBlocker(current, run.pages) ? <p className="hint">{pageBlocker(current, run.pages)}</p> : null}
            <Reasons reasons={current.reasons} />
            {next ? (
              <p className="hint" style={{ margin: 0 }}>
                Next: page {next.sequence}
                {next.integrated_page ? ` (p. ${next.integrated_page})` : ""} · {next.state.toLowerCase().replace("_", " ")}
                {next.state === "WAITING" ? ` until page ${current.sequence} is approved` : ""}
              </p>
            ) : (
              <p className="hint" style={{ margin: 0 }}>This is the last page of the run.</p>
            )}
          </div>
        ) : (
          <p className="hint">Every page of this run is approved.</p>
        )}
      </section>

      {stale.length ? (
        <div className="banner err">
          <p>
            <strong>
              {stale.length} page{stale.length === 1 ? " is" : "s are"} stale.
            </strong>{" "}
            Their approved art is kept; the sources they were built from changed. Open a page to see what changed and
            regenerate it when you choose.
          </p>
        </div>
      ) : null}

      <section className="block" aria-label="Contact sheet">
        <div className="block-head">
          <h2>
            Contact sheet <small>{run.pages.length} pages</small>
          </h2>
        </div>
        <div className="contact-sheet">
          {run.pages.map((page) => (
            <Link
              key={page.id}
              className="sheet-page"
              href={`${base}/pages/${page.id}`}
              data-current={page.id === run.next_page_id}
              title={pageBlocker(page, run.pages) ?? undefined}
            >
              <div className="sheet-thumb">
                {page.images ? (
                  // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
                  <img src={vaultImage(page.images.COLOR_FINISH)} alt={`Page ${page.sequence}`} loading="lazy" />
                ) : (
                  <span>{page.label ?? page.page_key}</span>
                )}
              </div>
              <div className="sheet-meta">
                <span className="tabular">
                  {page.sequence}
                  {page.integrated_page ? <span className="muted"> · p.{page.integrated_page}</span> : null}
                </span>
                <PageStateChip state={page.state} />
              </div>
            </Link>
          ))}
        </div>
      </section>

      <section className="block" aria-label="Run actions">
        <div className="block-head">
          <h2>Run</h2>
        </div>
        <RunActions run={run} />
      </section>
    </>
  );
}
