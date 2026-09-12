import Link from "next/link";
import { ApiUnreachableError, type AcquisitionOverview, type ScaffoldPlan, acquisition } from "@/lib/api";
import { formatBytes, relationLabel } from "@/lib/acquisition";
import { RefreshButton } from "./_components/RefreshButton";
import {
  ApiDown,
  CoveragePill,
  Empty,
  FamilyCard,
  Meter,
  MeterLegend,
  Pill,
  Provenance,
  RelationPill,
  Stat,
} from "./_components/ui";
import { refreshScaffoldAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function AcquisitionOverviewPage() {
  let data: AcquisitionOverview | null = null;
  let plan: ScaffoldPlan | null = null;
  let error: string | null = null;
  try {
    [data, plan] = await Promise.all([acquisition.overview(), acquisition.scaffold()]);
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  if (error) {
    return (
      <main style={{ padding: 0, maxWidth: "none" }}>
        <p className="eyebrow">Library</p>
        <h1 className="headline">Acquisition</h1>
        <ApiDown message={error} />
      </main>
    );
  }
  if (!data) return null;

  const { status, totals, families, relations } = data;
  const ordered = [...families].sort((a, b) => {
    const rank = (f: typeof a) => (f.missing + f.partial) / Math.max(1, f.works_total);
    return rank(b) - rank(a) || a.title.localeCompare(b.title);
  });
  const topRelations = Object.entries(relations).sort((a, b) => b[1] - a[1]);

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library</p>
      <h1 className="headline">Acquisition</h1>
      <p className="lede">
        What your library actually holds, what it is missing, and where the missing part may
        legally come from. Official is not the same as main canon: guidebooks, anthologies and
        colour editions are tracked as their own kind of material.
      </p>

      {!status.available ? (
        <Empty title="No acquisition data yet">
          <p>
            Continuum reads the documents the acquisition engine writes. Point it at a data
            directory with <code>CONTINUUM_ACQUISITION_DATA_DIR</code>, then run a scan to produce
            them.
          </p>
          <code className="cmd">python acquisition_orchestrator.py scan</code>
        </Empty>
      ) : (
        <>
          <div className="stats">
            <Stat label="source families" value={totals.families ?? 0} />
            <Stat label="official works" value={totals.official_works ?? 0} />
            <Stat label="complete" value={totals.complete ?? 0} tone="ok" />
            <Stat label="partial" value={totals.partial ?? 0} tone="warn" />
            <Stat label="missing" value={totals.missing ?? 0} tone="err" />
            <Stat label="files held" value={totals.files ?? 0} />
            <Stat label="on disk" value={formatBytes(totals.bytes ?? 0)} />
          </div>
          <div style={{ marginTop: 16 }}>
            <Meter
              complete={totals.complete ?? 0}
              partial={totals.partial ?? 0}
              missing={totals.missing ?? 0}
              unknown={totals.unknown ?? 0}
            />
            <MeterLegend />
          </div>

          <div className="section">
            <h2>What is in the library</h2>
            <span className="hint">
              {totals.legacy_paths ?? 0} legacy paths mapped · {totals.duplicate_groups ?? 0}{" "}
              duplicate groups reported
            </span>
          </div>
          <div className="pills">
            {topRelations.map(([relation, count]) => (
              <Pill key={relation} tone={relation === "MAIN_WORK" ? "accent" : "muted"}>
                {relationLabel(relation)} · {count}
              </Pill>
            ))}
          </div>

          <div className="section">
            <h2>Source families</h2>
            <span className="hint">least complete first</span>
          </div>
          {ordered.length ? (
            <div className="cards">
              {ordered.map((family) => (
                <FamilyCard key={family.id} family={family} />
              ))}
            </div>
          ) : (
            <Empty title="No families catalogued yet">
              <p>Run a scan and a discovery pass to populate the catalogue.</p>
            </Empty>
          )}

          <div className="split" style={{ marginTop: 34 }}>
            <div>
              <div className="section" style={{ marginTop: 0 }}>
                <h2>Next in the queue</h2>
                <Link href="/library/acquisition/queue" className="hint">
                  see the whole queue →
                </Link>
              </div>
              {data.queue_preview.length ? (
                <div className="rows">
                  {data.queue_preview.map((item) => (
                    <div className="row-item" key={item.work_id}>
                      <div className="row-main">
                        <div className="row-title">
                          <span>{item.work}</span>
                          <RelationPill relation={item.relation} />
                        </div>
                        <p className="row-meta">
                          {item.family}
                          {item.reason ? ` — ${item.reason}` : ""}
                        </p>
                      </div>
                      <div className="row-side">
                        {item.best_source ? <Pill>{item.best_source}</Pill> : null}
                        <CoveragePill status={item.coverage_status} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty title="Nothing pending">
                  <p>Every catalogued official work is accounted for.</p>
                </Empty>
              )}
            </div>

            <aside>
              <div className="section" style={{ marginTop: 0 }}>
                <h2>Attention</h2>
              </div>
              <div className="card" style={{ marginBottom: 14 }}>
                <h3>Folder structure</h3>
                <p className="sub" style={{ fontSize: 13, margin: "4px 0 12px" }}>
                  {plan && plan.create.length
                    ? `${plan.create.length} work folder${plan.create.length === 1 ? "" : "s"} are missing from the vault.`
                    : "Every accepted work has its folder."}
                </p>
                <RefreshButton
                  action={refreshScaffoldAction}
                  label="Recompute plan"
                  busyLabel="Computing…"
                />
                {plan && plan.command ? (
                  <>
                    <p className="row-meta" style={{ margin: "10px 0 4px" }}>
                      Creating them is a command you run — the vault is read-only to Continuum:
                    </p>
                    <code className="cmd">{plan.command}</code>
                  </>
                ) : null}
              </div>
              <div className="card" style={{ marginBottom: 14 }}>
                <h3>Recent updates</h3>
                {data.alerts.length ? (
                  <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13 }}>
                    {data.alerts.slice(0, 6).map((alert, index) => (
                      <li key={`${alert.at}-${index}`} style={{ marginBottom: 4 }}>
                        <span className="pill accent">{alert.kind.replaceAll("_", " ").toLowerCase()}</span>{" "}
                        {alert.detail}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="sub" style={{ fontSize: 13, margin: "4px 0 0" }}>
                    No changes seen since the last check.
                  </p>
                )}
                <p style={{ margin: "12px 0 0" }}>
                  <Link href="/library/acquisition/updates" className="hint">
                    update watch →
                  </Link>
                </p>
              </div>
              <div className="card">
                <h3>Waiting on you</h3>
                <div className="pills" style={{ marginTop: 8 }}>
                  <Pill tone={data.review_count ? "warn" : "muted"}>
                    {data.review_count} to review
                  </Pill>
                  <Pill tone={data.intake_pending ? "warn" : "muted"}>
                    {data.intake_pending} unidentified in intake
                  </Pill>
                  <Pill tone="muted">
                    {data.sources_enabled}/{data.sources_total} sources enabled
                  </Pill>
                </div>
                <p style={{ margin: "12px 0 0" }}>
                  <Link href="/library/acquisition/intake" className="hint">
                    intake and conflicts →
                  </Link>
                </p>
              </div>
            </aside>
          </div>
        </>
      )}

      <Provenance
        dataDir={status.data_dir}
        generatedAt={status.generated_at}
        vaultRoot={status.vault_root}
      />
    </main>
  );
}
