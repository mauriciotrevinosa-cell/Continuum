import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type ConstructionView, type StageView, manga, shortHash, vaultImage } from "@/lib/manga";
import { VaultNotFound, words } from "@/lib/vault";
import { ApiDown } from "../../../../../../library/acquisition/_components/ui";
import { PurposeBadge } from "../../../../../_parts/manga";
import { ComposePage, ConstructionRefresh, StageActions } from "./StageActions";

export const dynamic = "force-dynamic";

const STATE_TONE: Record<string, string> = {
  FROZEN: "ok",
  IN_REVIEW: "accent",
  READY: "info",
  QUEUED: "info",
  WAITING: "muted",
  STALE: "warn",
  FAILED: "err",
  BLOCKED: "err",
};

function StageCard({ pageId, panel, stage }: { pageId: string; panel: number; stage: StageView }) {
  const shown =
    stage.attempts.find((a) => a.id === stage.frozen_attempt_id && stage.frozen_valid) ??
    [...stage.attempts].reverse().find((a) => a.image) ??
    null;
  const latest = stage.attempts.at(-1) ?? null;
  return (
    <li className="stage-card" data-state={stage.state}>
      <div className="spread">
        <b>
          {stage.contract.order}. {words(stage.stage)}
        </b>
        <span className={`chip tiny ${STATE_TONE[stage.state] ?? "muted"}`}>{words(stage.state)}</span>
      </div>
      <div className="stage-thumb">
        {shown?.image ? (
          // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
          <img src={vaultImage(shown.image)} alt={`${stage.stage} attempt ${shown.attempt}`} loading="lazy" />
        ) : (
          <span>{stage.state === "QUEUED" ? "rendering…" : "not drawn"}</span>
        )}
      </div>
      {stage.reason ? <p className="hint warn-text">{stage.reason}</p> : null}
      <dl className="kv-inline small">
        <dt>May change</dt>
        <dd>{stage.contract.editable.join(", ")}</dd>
        <dt>Keeps</dt>
        <dd>{stage.contract.frozen_before.join(", ") || "nothing yet - first stage"}</dd>
        {shown ? (
          <>
            <dt>Attempt</dt>
            <dd>
              {shown.attempt}
              {stage.frozen_attempt_id === shown.id ? " (frozen)" : ""} ·{" "}
              {shown.output_class === "TEST_RENDER" ? "test render, never artwork" : words(shown.output_class ?? "")}
            </dd>
            <dt>Built on</dt>
            <dd>
              {shown.upstream
                ? `${words(shown.upstream.stage)} attempt ${shown.upstream.attempt} · ${shortHash(shown.upstream.sha256)}`
                : "the panel contract"}
            </dd>
            {shown.conditioning ? (
              <>
                <dt>Conditioned on</dt>
                <dd>
                  {shown.conditioning.scene
                    ? `${words(shown.conditioning.scene.purpose)} (${shown.conditioning.scene.references.length} scene ref)`
                    : "no scene reference"}
                  {Object.keys(shown.conditioning.identity).length
                    ? ` · identity: ${Object.keys(shown.conditioning.identity).join(", ")}`
                    : ""}
                </dd>
              </>
            ) : null}
            {shown.withheld.length ? (
              <>
                <dt>Withheld</dt>
                <dd title={shown.withheld.map((w) => `${w.role}: ${w.reason}`).join("; ")}>
                  {shown.withheld.length} reference(s) never sent - {shown.withheld[0].reason}
                </dd>
              </>
            ) : null}
            {shown.structure_drift !== null ? (
              <>
                <dt>Structure drift</dt>
                <dd title="Share of the upstream's edges this stage did not keep (advisory)">
                  {(shown.structure_drift * 100).toFixed(1)}%
                </dd>
              </>
            ) : null}
          </>
        ) : null}
        {latest && latest.id !== shown?.id ? (
          <>
            <dt>Latest</dt>
            <dd>
              attempt {latest.attempt} · {words(latest.state)}
              {latest.job?.error ? ` · ${latest.job.error}` : ""}
            </dd>
          </>
        ) : null}
      </dl>
      <details>
        <summary className="hint" style={{ cursor: "pointer" }}>
          Reference pack ({stage.pack.length})
        </summary>
        {stage.pack.length ? (
          <ul className="pack-list">
            {stage.pack.map((ref) => (
              <li key={`${ref.role}-${ref.reference_id}`}>
                <span className="chip tiny quiet">{words(ref.role)}</span> {ref.label || shortHash(ref.reference_id)}
                <span className="hint"> - {ref.why.join("; ")}</span>
                {ref.warnings.length ? <span className="hint warn-text"> ({ref.warnings.join(", ")})</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">
            No sorted, tagged references teach this stage yet. Tag references with the stage&apos;s techniques to
            give it evidence.
          </p>
        )}
      </details>
      <StageActions pageId={pageId} panel={panel} stage={stage} />
    </li>
  );
}

/**
 * Layered construction of one page: each panel's contract, then its stages in
 * build order - what each may change, what it keeps, what it was built on, the
 * evidence it was given - and the deterministic composition of the page.
 */
export default async function ConstructionPage({
  params,
}: {
  params: Promise<{ runId: string; pageId: string }>;
}) {
  const { runId, pageId } = await params;
  if (!/^[0-9a-f-]{36}$/.test(runId) || !/^[0-9a-f-]{36}$/.test(pageId)) notFound();
  let view: ConstructionView | null = null;
  let error: string | null = null;
  try {
    view = await manga.construction(pageId);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!view) return <ApiDown service="manga production" message={error ?? "no response"} />;
  if (view.run.id !== runId) notFound();
  const rendering = view.panels.some((p) => p.stages.some((s) => s.state === "QUEUED"));

  return (
    <>
      <Link className="crumb" href={`/production/runs/${runId}/pages/${pageId}`}>
        ← page
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">Layered construction</p>
          <h1 className="title">Panels, stage by stage</h1>
          <p className="row" style={{ gap: 8, margin: "6px 0" }}>
            <PurposeBadge purpose={view.run.purpose} />
            <ConstructionRefresh active={rendering} />
          </p>
          <p className="lead">
            Each stage builds on the frozen stage before it and may change only what its contract allows. Freezing a
            stage again makes every later stage stale; earlier stages stay valid. The page is composed from the
            frozen finishes - no diffusion - and lettered by Continuum.
          </p>
        </div>
        <ComposePage pageId={pageId} ready={view.compose.ready} blocked={view.compose.blocked} />
      </header>

      {view.panels.map(({ contract, stages }) => (
        <section key={contract.panel} className="block" aria-label={`Panel ${contract.panel}`}>
          <div className="block-head">
            <h2>
              Panel {contract.panel} <small>of {contract.panel_count}</small>
            </h2>
            <span className="hint mono">contract {shortHash(contract.hash)}</span>
          </div>
          <div className="surface panel stack">
            <p style={{ margin: 0 }}>
              <b>{words(contract.shot)}</b> - {contract.beat}
            </p>
            <dl className="kv-inline">
              <dt>Cast</dt>
              <dd>{contract.cast.join(", ") || "nobody - environment only"}</dd>
              <dt>Must show</dt>
              <dd>{contract.required.join("; ") || "-"}</dd>
              <dt>Never</dt>
              <dd>{contract.forbidden.join("; ")}</dd>
              <dt>Setting</dt>
              <dd>{contract.environment_tags.join(", ") || "none named"}</dd>
              {contract.calibration?.cal_id ? (
                <>
                  <dt>Calibration</dt>
                  <dd>
                    {contract.calibration.cal_id} · {contract.calibration.source_locator}
                  </dd>
                </>
              ) : null}
            </dl>
          </div>
          <ol className="stage-ladder">
            {stages.map((stage) => (
              <StageCard key={stage.stage} pageId={pageId} panel={contract.panel} stage={stage} />
            ))}
          </ol>
        </section>
      ))}
    </>
  );
}
