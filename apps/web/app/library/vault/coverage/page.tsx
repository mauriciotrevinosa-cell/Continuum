import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { type Coverage, type CoverageRoot, type RootStatus, catalog, collectionSlug, rootLabel } from "@/lib/catalog";
import { formatBytes } from "@/lib/acquisition";
import { ApiDown, Empty, PageHead } from "../../acquisition/_components/ui";
import { ScanControls } from "./ScanControls";

export const dynamic = "force-dynamic";

function Stat({ n, l, attention = false }: { n: number | string; l: string; attention?: boolean }) {
  return (
    <div className={`stat${attention ? " attention" : ""}`}>
      <span className="n">{typeof n === "number" ? n.toLocaleString() : n}</span>
      <span className="l">{l}</span>
    </div>
  );
}

function Rows({ title, rows }: { title: string; rows: { relative?: string; reason?: string | null; error?: string | null }[] }) {
  if (!rows.length) return null;
  return (
    <details className="disclosure" style={{ marginTop: 10 }}>
      <summary>
        {title} ({rows.length})
      </summary>
      <div className="disclosure-body">
        <ul className="exclusions">
          {rows.map((row) => (
            <li key={row.relative}>
              <code>{row.relative}</code>
              <span>{row.reason || row.error || "—"}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

function RootSection({ root, status }: { root: CoverageRoot; status: RootStatus | undefined }) {
  const byStatus = root.entries.by_status;
  const running = status?.active_jobs ?? [];
  const slug = collectionSlug(root.root_key);
  return (
    <section className="surface" style={{ padding: "22px 24px", marginBottom: 22 }}>
      <div className="section-title" style={{ marginTop: 0 }}>
        <h2>{rootLabel(root.root_key, root.collection)}</h2>
        {slug ? <Link href={`/library/vault/collections/${slug}`}>Collection import →</Link> : null}
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        {root.available ? "Reachable" : "Not reachable on this machine"} · last completed scan{" "}
        {root.last_completed_scan?.finished_at ? new Date(root.last_completed_scan.finished_at).toLocaleString() : "never"}
        {running.length ? ` · ${running.map((j) => `${j.job_type.replace("library.", "")} ${j.status.toLowerCase()} ${j.units_done}/${j.units_total ?? "?"}`).join(", ")}` : ""}
      </p>
      <div className="stat-grid">
        <Stat n={root.discovered.files} l={`files found · ${formatBytes(root.discovered.bytes)}`} />
        <Stat n={byStatus.CATALOGUED ?? 0} l="catalogued" />
        <Stat n={byStatus.UNSUPPORTED ?? 0} l="unsupported (with reasons)" attention={Boolean(byStatus.UNSUPPORTED)} />
        <Stat n={byStatus.FAILED ?? 0} l="failed (retried next scan)" attention={Boolean(byStatus.FAILED)} />
        <Stat n={byStatus.MISSING ?? 0} l="missing since an earlier scan" attention={Boolean(byStatus.MISSING)} />
        <Stat n={root.discovered.skipped} l="skipped by the scan" />
        <Stat n={root.archives.total} l="archives" />
        <Stat n={root.archives.members_indexed} l="archive members indexed" />
        <Stat n={root.units.by_kind.MANGA_CHAPTER ?? 0} l="manga chapters" />
        <Stat n={root.units.by_kind.EPISODE ?? 0} l="episodes" />
        <Stat n={root.units.by_kind.IMAGE ?? 0} l="images" />
        <Stat n={root.units.by_confidence.LOW ?? 0} l="uncertain identifications" attention={Boolean(root.units.by_confidence.LOW)} />
        <Stat n={root.duplicates.extra_copies} l="exact duplicate copies (linked)" />
        <Stat n={root.hashes.pending ?? 0} l="waiting for a hash" />
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        Archive views:{" "}
        {Object.entries(root.archives.by_view)
          .map(([k, v]) => `${v} ${k}`)
          .join(" · ") || "none"}
        {" · "}Hashes:{" "}
        {Object.entries(root.hashes)
          .map(([k, v]) => `${v} ${k.toLowerCase().replace("_", " ")}`)
          .join(" · ") || "none"}
      </p>
      <Rows title="Unsupported" rows={root.unsupported} />
      <Rows title="Failed" rows={root.failed} />
      <Rows title="Missing" rows={root.missing} />
      <Rows title="Skipped by the scan" rows={root.discovered.skipped_entries} />
      <Rows
        title="Uncertain identifications"
        rows={root.units.low_confidence.map((u) => ({ relative: `${u.relative} · ${u.label}`, reason: u.flags.join("; ") }))}
      />
      {Object.keys(root.units.episodes_by_series).length ? (
        <details className="disclosure" style={{ marginTop: 10 }}>
          <summary>Episodes and chapters by series</summary>
          <div className="disclosure-body">
            <ul className="exclusions">
              {Array.from(new Set([...Object.keys(root.units.chapters_by_series), ...Object.keys(root.units.episodes_by_series)]))
                .sort()
                .map((title) => (
                  <li key={title}>
                    <span>{title}</span>
                    <span>
                      {root.units.chapters_by_series[title] ?? 0} chapters · {root.units.episodes_by_series[title] ?? 0} episodes
                    </span>
                  </li>
                ))}
            </ul>
          </div>
        </details>
      ) : null}
    </section>
  );
}

/**
 * Can we account for the whole Vault? Every file found, where it ended up, and
 * why anything is not searchable - read from the catalog itself.
 */
export default async function CoveragePage() {
  let coverage: Coverage | null = null;
  let roots: RootStatus[] = [];
  let error: string | null = null;
  try {
    [coverage, roots] = await Promise.all([catalog.coverage(), catalog.roots()]);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const active = roots.some((root) => root.active_jobs.length > 0);
  const t = coverage?.totals ?? {};

  return (
    <>
      <PageHead
        eyebrow="Vault"
        title="Coverage"
        lead="Every file under every catalog folder, where it ended up, and why anything is not searchable. Scans are incremental: unchanged files are never reopened or re-hashed."
        aside={roots.length ? <ScanControls rootKeys={roots.map((r) => r.root_key)} active={active} /> : null}
      />
      {error ? <ApiDown service="catalog" message={error} /> : null}
      {coverage ? (
        <>
          <div className="stat-grid">
            <Stat n={t.files_discovered ?? 0} l="files found" />
            <Stat n={t.catalogued ?? 0} l="catalogued" />
            <Stat n={(t.unsupported ?? 0) + (t.failed ?? 0) + (t.missing ?? 0)} l="not searchable, each with a reason" />
            <Stat n={t.unaccounted ?? 0} l="not yet accounted for" attention={Boolean(t.unaccounted)} />
            <Stat n={t.units ?? 0} l="searchable units" />
            <Stat n={t.archive_members_indexed ?? 0} l="archive members indexed" />
          </div>
          <p className="muted" style={{ fontSize: 13 }}>
            Generated {new Date(coverage.generated_at).toLocaleString()}. The same report, as JSON and Markdown, is written to
            ContinuumData/generated/reports/catalog after every scan. It names your files, so it stays on this machine.
          </p>
          {coverage.roots.map((root) => (
            <RootSection key={root.root_key} root={root} status={roots.find((r) => r.root_key === root.root_key)} />
          ))}
        </>
      ) : error ? null : (
        <Empty title="No catalog folders are configured">
          <p>Set CONTINUUM_SOURCE_VAULT_ROOT (and optionally CONTINUUM_INTAKE_ROOTS), then restart the API and worker.</p>
        </Empty>
      )}
    </>
  );
}
