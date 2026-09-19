import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import {
  type PageAttempt,
  type PageDetail,
  type RunView,
  manga,
  pageBlocker,
  shortHash,
} from "@/lib/manga";
import { VaultNotFound, words } from "@/lib/vault";
import { ApiDown } from "../../../../../library/acquisition/_components/ui";
import { ByAuthority, ObservationCard, PageStateChip, PurposeBadge, Reasons } from "../../../../_parts/manga";
import { PageRefGrid } from "../../../../_parts/refs";
import { CastEditor, FinishViewer, JobStatus, PageActions } from "./PageActions";

export const dynamic = "force-dynamic";

function Provenance({ attempt }: { attempt: PageAttempt }) {
  const p = attempt.artwork_provenance as {
    backend?: string;
    provider_id?: string;
    model?: Record<string, string>;
    workflow?: Record<string, string>;
    settings?: Record<string, unknown>;
    master_sha256?: string;
    references?: { role: string; reference_id: string; character: string | null }[];
  };
  const roles = new Map<string, number>();
  for (const r of p.references ?? []) roles.set(r.role, (roles.get(r.role) ?? 0) + 1);
  return (
    <dl className="kv-inline">
      <dt>Output</dt>
      <dd>{attempt.output_class === "TEST_RENDER" ? "Test render - a labelled diagram, never artwork" : words(attempt.output_class)}</dd>
      <dt>Backend</dt>
      <dd>
        {p.backend ?? "?"} · <span className="mono">{p.provider_id ?? "?"}</span>
      </dd>
      <dt>Model</dt>
      <dd>
        {p.model ? `${p.model.name ?? "?"} ${p.model.version ?? ""}` : "none (test renderer)"}
        {p.model?.sha256 ? <span className="mono"> · {shortHash(p.model.sha256)}</span> : null}
        {p.model?.license ? ` · ${p.model.license}` : ""}
      </dd>
      <dt>Workflow</dt>
      <dd>
        {p.workflow ? `${p.workflow.id ?? p.workflow.name ?? ""} v${p.workflow.version ?? "?"}` : String((p as Record<string, unknown>).workflow ?? "?")}
        {p.workflow?.sha256 ? <span className="mono"> · {shortHash(p.workflow.sha256)}</span> : null}
      </dd>
      <dt>Seed</dt>
      <dd className="tabular">{attempt.seed ?? "?"}</dd>
      <dt>Master</dt>
      <dd className="mono">{shortHash(p.master_sha256)}</dd>
      <dt>References sent</dt>
      <dd>{[...roles.entries()].map(([role, count]) => `${count} ${role.toLowerCase()}`).join(" · ") || "none"}</dd>
    </dl>
  );
}

/**
 * The current page: its script and lineage, the reference bundle it will be
 * drawn from (by role and authority), the attempts with their finishes and
 * provenance, and the review actions its state allows.
 */
export default async function ProductionPageView({ params }: { params: Promise<{ runId: string; pageId: string }> }) {
  const { runId, pageId } = await params;
  if (!/^[0-9a-f-]{36}$/.test(runId) || !/^[0-9a-f-]{36}$/.test(pageId)) notFound();
  let page: PageDetail | null = null;
  let run: RunView | null = null;
  let error: string | null = null;
  try {
    [page, run] = await Promise.all([manga.page(pageId), manga.run(runId)]);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!page || !run) return <ApiDown service="manga production" message={error ?? "no response"} />;
  if (page.run_id !== run.id) notFound();
  const { body, bundle } = page;
  const latest = page.attempts[0] ?? null;
  const approved = page.attempts.find((a) => a.id === page.approved_attempt_id) ?? null;
  // The newest attempt that has been drawn (a queued attempt has no finishes yet).
  const shown = page.attempts.find((a) => a.state !== "QUEUED") ?? approved;
  const blocker = pageBlocker(page, run.pages);
  const previous = run.pages.find((p) => p.sequence === page.sequence - 1);
  const following = run.pages.find((p) => p.sequence === page.sequence + 1);
  const testBackend =
    run.purpose === "WORKFLOW_TEST" ||
    (latest?.output_class ?? "TEST_RENDER") === "TEST_RENDER" ||
    String((run.profile.body.backend as Record<string, unknown> | undefined)?.provider_id ?? "").startsWith("fake.");
  const base = `/production/runs/${run.id}`;

  return (
    <>
      <Link className="crumb" href={base}>
        ← {run.episode}
        {run.chapter ? ` chapter ${run.chapter}` : ""} run
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">
            {run.project_key} · {run.episode} · page {page.sequence} of {run.pages.length}
          </p>
          <h1 className="title">
            Page {page.sequence}
            {page.integrated_page ? <span className="muted"> · p. {page.integrated_page}</span> : null}
          </h1>
          <p className="row" style={{ gap: 8, margin: "6px 0" }}>
            <PurposeBadge purpose={run.purpose} />
            <PageStateChip state={page.state} />
            {body.origin === "overlay" ? <span className="chip warn">Overlay insertion</span> : null}
            {body.chapter_end ? <span className="chip quiet">Chapter end</span> : null}
          </p>
          <p className="lead">
            {body.label ?? body.scene ?? page.page_key} <span className="muted mono">· {page.page_key}</span>
          </p>
        </div>
        <span className="row">
          <Link className="button small" href={`${base}/pages/${page.id}/construction`}>
            Layered construction
          </Link>
          {previous ? (
            <Link className="button small ghost" href={`${base}/pages/${previous.id}`}>
              ← Page {previous.sequence}
            </Link>
          ) : null}
          {following ? (
            <Link className="button small ghost" href={`${base}/pages/${following.id}`}>
              Page {following.sequence} →
            </Link>
          ) : null}
        </span>
      </header>

      {blocker ? (
        <div className={`banner${page.state === "BLOCKED" ? " err" : ""}`}>
          <p>
            <strong>{page.state === "BLOCKED" ? "Blocked." : "Waiting."}</strong> {blocker}
            {page.state === "WAITING" && previous ? (
              <>
                {" "}
                <Link href={`${base}/pages/${previous.id}`}>Open page {previous.sequence}</Link>
              </>
            ) : null}
          </p>
        </div>
      ) : null}
      {page.state === "STALE" ? (
        <div className="banner err">
          <p>
            <strong>Stale.</strong> The approved art is kept; what it was built from changed:
          </p>
          <Reasons reasons={page.reasons} />
        </div>
      ) : null}

      <div className="page-work">
        <section className="stack" aria-label="Art">
          <JobStatus attempt={latest} testBackend={testBackend} />
          {shown ? (
            <>
              <FinishViewer attempt={shown} />
              <span className="hint">
                Showing attempt {shown.attempt}
                {shown.id === page.approved_attempt_id ? " (approved)" : ""} · {words(shown.state)}
              </span>
            </>
          ) : (
            <div className="finish-frame">
              <p className="hint" style={{ padding: 24 }}>
                Nothing drawn yet.
              </p>
            </div>
          )}
          {page.state !== "WAITING" && page.state !== "BLOCKED" ? (
            <PageActions pageId={page.id} state={page.state} purpose={run.purpose} latest={latest} />
          ) : null}

          <div className="block-head">
            <h2>
              Attempts <small>{page.attempts.length}</small>
            </h2>
          </div>
          {page.attempts.length ? (
            <div className="stack">
              {page.attempts.map((attempt) => (
                <details key={attempt.id} className="surface panel" open={attempt === latest}>
                  <summary className="spread" style={{ cursor: "pointer" }}>
                    <span>
                      Attempt {attempt.attempt}
                      {attempt.id === page.approved_attempt_id ? " · approved" : ""}
                    </span>
                    <span className="chips">
                      <span className="chip quiet">{words(attempt.display_state)}</span>
                      {attempt.output_class === "TEST_RENDER" ? <span className="chip warn">Test render</span> : null}
                    </span>
                  </summary>
                  <div className="stack" style={{ marginTop: 10 }}>
                    <Provenance attempt={attempt} />
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <p className="hint">No attempts yet.</p>
          )}
        </section>

        <section className="stack" aria-label="Script and references">
          <div className="surface panel stack">
            <strong>Cast - derived from the script</strong>
            <dl className="kv-inline">
              <dt>Present</dt>
              <dd>{body.plan.characters_present.join(", ") || "nobody named"}</dd>
              <dt>Primary</dt>
              <dd>{body.plan.primary_character ?? "-"}</dd>
              <dt>Supporting</dt>
              <dd>{body.plan.supporting_characters.join(", ") || "-"}</dd>
              <dt>Speakers</dt>
              <dd>{body.plan.speakers.join(", ") || "silent page"}</dd>
              <dt>From</dt>
              <dd>
                script: {body.plan.cast_source.script.join(", ") || "-"} · dialogue:{" "}
                {body.plan.cast_source.dialogue.join(", ") || "-"}
                {body.plan.cast_source.override ? " · corrected by a person" : ""}
              </dd>
              <dt>Primary intent</dt>
              <dd>{body.plan.primary_intent ? words(body.plan.primary_intent) : "-"}</dd>
              <dt>Setting tags</dt>
              <dd>{body.plan.environment_tags.join(", ") || "none named"}</dd>
            </dl>
            {body.plan.uncertain.length ? (
              <ul className="warn-list">
                {body.plan.uncertain.map((u) => (
                  <li key={u} className="warn">
                    {u}
                  </li>
                ))}
              </ul>
            ) : null}
            <CastEditor
              pageId={page.id}
              plan={body.plan}
              known={[...new Set([...bundle.characters.map((c) => c.name), ...body.plan.characters_present])]}
            />
          </div>

          <div className="surface panel script-block">
            <strong>Script</strong>
            {body.scene ? <span className="muted">{body.scene}</span> : null}
            {body.directions.length ? (
              <ul>
                {body.directions.map((d, index) => (
                  <li key={index}>{d}</li>
                ))}
              </ul>
            ) : null}
            {body.dialogue.length ? (
              <div className="stack" style={{ gap: 6 }}>
                {body.dialogue.map((line, index) => (
                  <div key={index} className={`dialogue-line${line.kind === "internal_noise" ? " noise" : ""}`}>
                    <span className="who">{line.kind === "internal_noise" ? "noise" : line.speaker || "-"}</span>
                    <span className="what">{line.text}</span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="hint">No dialogue on this page.</span>
            )}
            {body.constraints.length ? (
              <ul>
                {body.constraints.map((c) => (
                  <li key={c} className="constraint">
                    {c}
                  </li>
                ))}
              </ul>
            ) : null}
            <span className="muted" style={{ fontSize: 12.5 }}>
              Intents: {body.intents.map(words).join(", ") || "none"} · Characters: {body.characters.join(", ") || "none"}
            </span>
          </div>

          <div className="surface panel stack">
            <strong>Lineage</strong>
            <dl className="kv-inline">
              {body.origin === "base" ? (
                <>
                  <dt>Panel script</dt>
                  <dd>
                    {body.lineage.document_id} {body.lineage.version ? `v${body.lineage.version}` : ""} · base page{" "}
                    {body.base_page}
                    {body.lineage.commit ? <span className="mono"> · {shortHash(String(body.lineage.commit))}</span> : null}
                  </dd>
                </>
              ) : (
                <>
                  <dt>Overlay</dt>
                  <dd>
                    {body.lineage.overlay?.document_id ?? "?"} {body.lineage.overlay?.version ? `v${body.lineage.overlay.version}` : ""}
                    {body.insertion ? ` · ${body.insertion.item_key}` : ""}
                  </dd>
                  <dt>Placement</dt>
                  <dd>
                    after base page {String(body.lineage.after_base_page ?? "?")}
                    {body.insertion && "status" in body.insertion ? ` · ${String((body.insertion as Record<string, unknown>).status).toLowerCase()}` : ""}
                  </dd>
                </>
              )}
              <dt>Profile</dt>
              <dd>
                {bundle.profile.name} v{bundle.profile.version}
              </dd>
              <dt>Continuity</dt>
              <dd>
                v{bundle.continuity.version} · {bundle.continuity.approved_pages.length} approved page
                {bundle.continuity.approved_pages.length === 1 ? "" : "s"}
              </dd>
            </dl>
            {page.dependencies.length ? (
              <details>
                <summary className="hint" style={{ cursor: "pointer" }}>
                  Built from {page.dependencies.length} dependencies
                </summary>
                <dl className="kv-inline" style={{ marginTop: 8 }}>
                  {page.dependencies.map((d) => (
                    <div key={`${d.kind}-${d.key}`} style={{ display: "contents" }}>
                      <dt>{words(d.kind)}</dt>
                      <dd>
                        {d.key} <span className="mono muted">{shortHash(d.version_hash)}</span>
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            ) : null}
          </div>

          <div className="surface panel stack">
            <strong>Characters</strong>
            {bundle.characters.length ? (
              bundle.characters.map((c) => (
                <div key={c.character_id} className="stack">
                  <div className="spread">
                    <Link href={`/library/characters/${c.character_id}`}>
                      <b>{c.name}</b>
                    </Link>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {c.observations.length} of {c.available_observations} observations · needs{" "}
                      {c.need.facets.map(words).join(", ")}
                      {c.need.angles.length ? ` · ${c.need.angles.map(words).join(", ")}` : ""}
                    </span>
                  </div>
                  {c.forbidden.length ? <span className="constraint">{c.forbidden.join(" · ")}</span> : null}
                  <ByAuthority observations={c.observations} empty="No observations retrieved." />
                  {c.stylization_observations.length ? (
                    <div className="stack">
                      <span className="eyebrow" style={{ margin: 0 }}>
                        Stylization - never identity
                      </span>
                      <div className="obs-grid">
                        {c.stylization_observations.map((o) => (
                          <ObservationCard key={o.id} observation={o} />
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              ))
            ) : (
              <p className="hint">No grounded character on this page.</p>
            )}
          </div>

          <div className="surface panel stack">
            <strong>Continuity references</strong>
            {bundle.continuity.approved_pages.length ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {bundle.continuity.approved_pages.map((a) => (
                  <li key={a.attempt_id}>
                    Page {a.sequence} · {a.page_key} <span className="mono muted">{shortHash(a.master_sha256)}</span>
                    {a.output_class === "TEST_RENDER" ? <span className="muted"> · test render</span> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">No approved pages in this run yet.</p>
            )}
          </div>

          <div className="surface panel stack">
            <strong>Full source pages - page craft, never identity</strong>
            <span className="hint">
              Complete manga pages selected to teach structure and technique by abstraction - never a composition to
              copy, and never evidence of what a character looks like.
            </span>
            <span className="eyebrow" style={{ margin: 0 }}>
              Grammar
            </span>
            <PageRefGrid refs={bundle.grammar} empty="No grammar pages for this page." />
            <span className="eyebrow" style={{ margin: 0 }}>
              Technique
            </span>
            <PageRefGrid refs={bundle.technique ?? []} empty="No technique pages for this page's intents." />
          </div>

          <div className="surface panel stack">
            <strong>Environment - never overrides the setting canon</strong>
            {bundle.environment.length ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {bundle.environment.map((e) => (
                  <li key={e.reference_id}>
                    <Link href={`/library/references/${e.reference_id}`}>{e.label || e.reference_id}</Link> · matched{" "}
                    {e.matched.join(", ")} <span className="muted">· teaches {e.teaches.map(words).join(", ")}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">No tagged environment references match this page.</p>
            )}
            {bundle.environment_pages?.length ? (
              <>
                <span className="eyebrow" style={{ margin: 0 }}>
                  Unverified wide pages from the cast&apos;s source world
                </span>
                <PageRefGrid refs={bundle.environment_pages} empty="" />
              </>
            ) : null}
            {bundle.gaps.length ? (
              <ul className="hint" style={{ margin: 0, paddingLeft: 18 }}>
                {bundle.gaps.map((g) => (
                  <li key={g}>Gap: {g}</li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>
      </div>
    </>
  );
}
