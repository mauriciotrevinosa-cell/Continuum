import Link from "next/link";
import { ApiUnreachableError, projects as projectsApi } from "@/lib/api";
import { type ContinueItem, type RootStatus, type SeriesSummary, catalog, rootLabel } from "@/lib/catalog";
import { plural } from "@/lib/acquisition";
import { StudioShell } from "./_studio/StudioShell";
import { ApiDown, Empty, PageHead } from "./library/acquisition/_components/ui";
import { ContinueCard, SearchBox, SeriesCard } from "./library/vault/_parts";

export const dynamic = "force-dynamic";

function scanState(root: RootStatus): string {
  const running = root.active_jobs.find((job) => job.status === "RUNNING");
  if (running) {
    const done = running.units_total ? ` ${running.units_done}/${running.units_total}` : "";
    return running.job_type.endsWith("hash") ? `Hashing${done}` : running.job_type.endsWith("import") ? `Importing${done}` : `Scanning${done}`;
  }
  if (root.active_jobs.length) return "Queued";
  if (!root.last_scan) return "Never scanned";
  if (root.last_scan.status !== "COMPLETED") return "Scan interrupted";
  return `${plural(root.last_scan.files ?? 0, "file")} · scanned ${new Date(root.last_scan.finished_at ?? root.last_scan.started_at).toLocaleDateString()}`;
}

/**
 * The studio: pick up where you left off, search everything, open a series.
 *
 * Everything shown is read from the catalog of the configured Vault and intake
 * folders; nothing here is specific to any project or any series.
 */
export default async function StudioHome() {
  let items: ContinueItem[] = [];
  let series: SeriesSummary[] = [];
  let roots: RootStatus[] = [];
  let projects: { id: string; title: string; documents: number }[] = [];
  let error: string | null = null;
  try {
    [items, series, roots] = await Promise.all([catalog.continueItems(), catalog.series(), catalog.roots()]);
    projects = (await projectsApi.list().catch(() => [])).map((p) => ({ id: p.id, title: p.title, documents: p.documents }));
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const inProgress = series.filter((s) => s.last_opened_at);

  return (
    <StudioShell>
      <PageHead
        eyebrow="Continuum Studio"
        title="Studio"
        lead="Your Vault, references and projects in one place. The Vault is read-only here: Continuum catalogs it, never changes it."
        aside={
          <Link className="button" href="/library/vault/coverage">
            Coverage
          </Link>
        }
      />
      {error ? <ApiDown service="studio" message={error} /> : null}
      <SearchBox />

      {items.length ? (
        <>
          <div className="section-title">
            <h2>Continue</h2>
          </div>
          <div className="continue-row">
            {items.slice(0, 8).map((item) => (
              <ContinueCard key={`${item.progress.unit_key}-${item.state}`} item={item} />
            ))}
          </div>
        </>
      ) : null}

      <div className="section-title">
        <h2>Folders</h2>
        <Link href="/library/vault/coverage">Scan and coverage →</Link>
      </div>
      <div className="stat-grid">
        {roots.map((root) => (
          <div key={root.root_key} className={`stat${root.available ? "" : " attention"}`}>
            <span className="n" style={{ fontSize: 16 }}>
              {rootLabel(root.root_key, root.collection)}
            </span>
            <span className="l">{root.available ? scanState(root) : "Not reachable on this machine"}</span>
            {root.root_key.startsWith("intake:") ? (
              <span className="l">
                {" · "}
                <Link href={`/library/vault/collections/${root.root_key.slice(7)}`}>Collection</Link>
              </span>
            ) : null}
          </div>
        ))}
        <div className="stat">
          <span className="n" style={{ fontSize: 16 }}>
            References
          </span>
          <span className="l">
            <Link href="/library/references">Browse</Link> · <Link href="/library/inbox">Inbox</Link>
          </span>
        </div>
        {projects.map((project) => (
          <div key={project.id} className="stat">
            <span className="n" style={{ fontSize: 16 }}>
              {project.title}
            </span>
            <span className="l">
              <Link href={`/projects/${project.id}`}>{plural(project.documents, "document")}</Link>
            </span>
          </div>
        ))}
      </div>

      {inProgress.length ? (
        <>
          <div className="section-title">
            <h2>In progress</h2>
          </div>
          <div className="series-grid">
            {inProgress.map((s) => (
              <SeriesCard key={s.series_key} series={s} />
            ))}
          </div>
        </>
      ) : null}

      <div className="section-title">
        <h2>Series in the Vault</h2>
        <Link href="/library/vault">Browse all →</Link>
      </div>
      {series.length ? (
        <div className="series-grid">
          {series.slice(0, 24).map((s) => (
            <SeriesCard key={s.series_key} series={s} />
          ))}
        </div>
      ) : error ? null : (
        <Empty title="The catalog is empty">
          <p>
            Scan the Source Vault from <Link href="/library/vault/coverage">Coverage</Link>. The scan
            runs in the worker; it reads your files and never changes them.
          </p>
        </Empty>
      )}
    </StudioShell>
  );
}
