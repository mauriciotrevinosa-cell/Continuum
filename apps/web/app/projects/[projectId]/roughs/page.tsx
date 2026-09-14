import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type Readiness, type RoughArtifact, type RoughCompletion, vault } from "@/lib/vault";
import { ApiDown, Empty } from "../../../library/acquisition/_components/ui";
import { loadProject } from "../../_components/project";
import { ReadinessBanner, STATE_TONE, TestOnlyChip, stateLabel } from "../../../production/_parts/status";
import { CreateArtifact } from "./CreateArtifact";

export const dynamic = "force-dynamic";

function Verdict({ artifact }: { artifact: RoughArtifact }) {
  const latest = artifact.attempts[0];
  if (artifact.final_approved_attempt_id) return <span className="chip ok">Final approved</span>;
  if (artifact.creative_approved_attempt_id) return <span className="chip ok">Creative approved</span>;
  if (artifact.technical_pass_attempt_id) return <span className="chip info">Technical pass · workflow verified</span>;
  if (!latest) return <span className="chip muted">No attempts</span>;
  return <span className={`chip ${STATE_TONE[latest.display_state] ?? "muted"}`}>{stateLabel(latest.display_state)}</span>;
}

/**
 * The manual rough workspace for this project: one page or panel at a time.
 *
 * This is the advanced / override tool - masks, source-derived edits, chosen
 * references and seeds, one-page corrections. It is not how hundreds of pages
 * get made; production from chapter packages is a separate, batch workflow.
 */
export default async function RoughsPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  let artifacts: RoughArtifact[] = [];
  let completion: RoughCompletion | null = null;
  let error: string | null = null;
  let readiness: Readiness | null = null;
  const detail = await loadProject(projectId).catch(() => null);
  if (!detail) notFound();
  try {
    [artifacts, readiness, completion] = await Promise.all([
      vault.artifacts(projectId),
      vault.readiness(),
      vault.roughCompletion(projectId),
    ]);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const titles = new Map(detail.episodes.map((e) => [e.code, e]));
  const scripts = detail.documents
    .filter((d) => d.category === "panel-script" && ["APPROVED", "LOCKED"].includes(d.lifecycle))
    .sort((a, b) => (a.episode ?? "").localeCompare(b.episode ?? "", undefined, { numeric: true }))
    .map((d) => {
      const episode = d.episode ? titles.get(d.episode) : undefined;
      const pages = d.facts.pages ? ` · ${d.facts.pages} pp.` : "";
      return {
        id: d.id,
        episode: d.episode ?? "",
        label: `${d.episode ?? "?"} · ${episode?.title ?? d.title}${pages}${d.version ? ` · v${d.version}` : ""}`,
      };
    });
  const production = artifacts.filter((a) => !a.test_only);
  const tests = artifacts.filter((a) => a.test_only);

  const row = (artifact: RoughArtifact) => (
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
      <span className="side chips">
        <TestOnlyChip purpose={artifact.purpose} />
        <Verdict artifact={artifact} />
      </span>
    </Link>
  );

  return (
    <>
      <header className="page-head" style={{ marginTop: 28 }}>
        <div>
          <p className="eyebrow">Manga · advanced / override workspace</p>
          <h1 className="title">Roughs</h1>
          <p className="lead">
            Work on one page or panel by hand: a reference bundle, a source plate with masks, chosen
            references and seeds, then review. Use it for difficult panels, source-derived edits and
            one-page corrections. It is not the way to produce whole chapters - that starts from a
            chapter package and runs as a batch.
          </p>
        </div>
      </header>
      {error ? <ApiDown service="production" message={error} /> : null}
      <ReadinessBanner readiness={readiness} />

      {completion ? (
        <div className="surface panel stack" style={{ marginBottom: 22 }}>
          <strong>Rough manga completion counts production pages only</strong>
          <p className="sub" style={{ margin: 0 }}>
            Production: {completion.production.artifacts} page/panel
            {completion.production.artifacts === 1 ? "" : "s"} · {completion.production.creative_approved} creative
            approved · {completion.production.final_approved} final approved.{" "}
            <span className="muted">
              Not counted: {completion.workflow_tests.artifacts} workflow test
              {completion.workflow_tests.artifacts === 1 ? "" : "s"} ({completion.workflow_tests.technical_pass} with a
              technical pass) and {completion.non_canon_samples.artifacts} non-canon sample
              {completion.non_canon_samples.artifacts === 1 ? "" : "s"}.
            </span>
          </p>
        </div>
      ) : null}

      {production.length ? (
        <section style={{ marginBottom: 22 }}>
          <div className="block-head">
            <h2>
              Production pages and panels <small>{production.length}</small>
            </h2>
          </div>
          <div className="list">{production.map(row)}</div>
        </section>
      ) : null}
      {tests.length ? (
        <section style={{ marginBottom: 28 }}>
          <div className="block-head">
            <h2>
              Workflow tests and samples <small>{tests.length} · non-canon, never counted</small>
            </h2>
          </div>
          <div className="list">{tests.map(row)}</div>
        </section>
      ) : null}
      {!artifacts.length && !error ? (
        <div style={{ marginBottom: 28 }}>
          <Empty title="No roughs yet">
            <p>Pick a page from a panel script to start - a small slice first, not the whole chapter.</p>
          </Empty>
        </div>
      ) : null}
      <CreateArtifact
        projectId={projectId}
        scripts={scripts}
        defaultPurpose={readiness?.is_fake ? "WORKFLOW_TEST" : "PRODUCTION"}
      />
      <p className="muted" style={{ marginTop: 10, fontSize: 13 }}>
        {scripts.length} approved panel script{scripts.length === 1 ? "" : "s"} from the
        project&apos;s committed documents.
      </p>
    </>
  );
}
