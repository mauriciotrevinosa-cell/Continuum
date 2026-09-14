import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { COLLECTION_SLUG, CatalogNotFound, type ImportReport, type RootStatus, catalog } from "@/lib/catalog";
import { words } from "@/lib/vault";
import { ApiDown, PageHead } from "../../../acquisition/_components/ui";
import { ImportControls } from "./ImportControls";

export const dynamic = "force-dynamic";

function List({ title, items }: { title: string; items: { key: string; left: string; right?: string | null }[] }) {
  return (
    <details className="disclosure" style={{ marginTop: 10 }}>
      <summary>
        {title} ({items.length})
      </summary>
      <div className="disclosure-body">
        {items.length ? (
          <ul className="exclusions">
            {items.map((item) => (
              <li key={item.key}>
                <code>{item.left}</code>
                <span>{item.right ?? ""}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">None.</p>
        )}
      </div>
    </details>
  );
}

/**
 * One intake collection (for example collected fan art): what its import did,
 * file by file, and the defaults it applied. The folder itself is only read.
 */
export default async function CollectionPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!COLLECTION_SLUG.test(slug)) notFound();
  let report: ImportReport | null = null;
  let root: RootStatus | undefined;
  let error: string | null = null;
  try {
    [report, root] = await Promise.all([
      catalog.importReport(slug),
      catalog.roots().then((roots) => roots.find((r) => r.root_key === `intake:${slug}`)),
    ]);
  } catch (cause) {
    if (cause instanceof CatalogNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!report) return <ApiDown service="catalog" message={error ?? "unavailable"} />;
  const t = report.totals;
  const active = Boolean(root?.active_jobs.length);

  return (
    <>
      <Link className="crumb" href="/library/vault/coverage">
        ← Coverage
      </Link>
      <PageHead
        eyebrow="Collection"
        title={report.collection}
        lead={`Imported with: ${Object.entries(report.defaults)
          .map(([k, v]) => `${words(k)} ${v.toLowerCase().replaceAll("_", " ")}`)
          .join(" · ")}. Nothing is approved for model training by importing.`}
        aside={<ImportControls slug={slug} active={active} />}
      />
      <div className="stat-grid">
        <div className="stat">
          <span className="n">{t.discovered}</span>
          <span className="l">files in the folder</span>
        </div>
        <div className="stat">
          <span className="n">{t.imported_images_as_references}</span>
          <span className="l">
            images → <Link href={`/library/references?origin=FAN_ART`}>references</Link>
          </span>
        </div>
        <div className="stat">
          <span className="n">{t.imported_clips_as_inbox_candidates}</span>
          <span className="l">
            clips → <Link href="/library/inbox?kind=VIDEO">Inbox</Link>
          </span>
        </div>
        <div className="stat">
          <span className="n">{t.exact_duplicates_linked + t.already_in_library_linked}</span>
          <span className="l">exact duplicates linked</span>
        </div>
        <div className={`stat${t.rejected ? " attention" : ""}`}>
          <span className="n">{t.rejected}</span>
          <span className="l">rejected</span>
        </div>
        <div className={`stat${t.failed ? " attention" : ""}`}>
          <span className="n">{t.failed}</span>
          <span className="l">failed</span>
        </div>
        <div className="stat">
          <span className="n">{t.not_imported_yet}</span>
          <span className="l">not imported yet</span>
        </div>
      </div>
      <p className="muted" style={{ fontSize: 13 }}>
        Formats by content: {Object.entries(report.formats).map(([k, v]) => `${v} ${k}`).join(" · ")}
      </p>
      <List title="Rejected" items={report.rejected.map((r) => ({ key: r.file, left: r.file, right: r.reason }))} />
      <List title="Failed" items={report.failed.map((r) => ({ key: r.file, left: r.file, right: r.reason }))} />
      <List
        title="Exact duplicates"
        items={report.duplicates.map((r) => ({ key: r.file, left: r.file, right: r.duplicate_of ? `same bytes as ${r.duplicate_of}` : null }))}
      />
      <List title="Unknown creator" items={report.unknown_creator.map((f) => ({ key: f, left: f }))} />
      <List title="Unknown date" items={report.unknown_date.map((f) => ({ key: f, left: f }))} />
      <List
        title="Named as another format"
        items={report.extension_mismatches.map((r) => ({ key: r.file, left: r.file, right: r.detail }))}
      />
    </>
  );
}
