import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { type ReadableSeriesSummary, listReadableSeries } from "@/lib/series";
import { ApiDown, Empty, PageHead } from "../library/acquisition/_components/ui";

export const dynamic = "force-dynamic";

export default async function SeriesPage() {
  let series: ReadableSeriesSummary[] = [];
  let error: string | null = null;

  try {
    series = await listReadableSeries();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  return (
    <>
      <PageHead
        eyebrow="Reading"
        title="Series"
        lead="Clean reading editions of the stories you make. Production drafts, audits and voice checks stay in Projects."
      />

      {error ? <ApiDown service="Series" message={error} /> : null}

      {series.length ? (
        <div className="reading-series-grid">
          {series.map((item) => (
            <Link key={item.project.id} className="reading-series-card" href={`/series/${encodeURIComponent(item.project.id)}`}>
              <p className="eyebrow">Light Novel</p>
              <h2>{item.project.title}</h2>
              {item.project.logline ? <p className="reading-series-logline">{item.project.logline}</p> : null}
              <div className="reading-series-meta">
                <span>{item.volumes} volume{item.volumes === 1 ? "" : "s"}</span>
                <span>{item.chapters} chapters</span>
              </div>
            </Link>
          ))}
        </div>
      ) : error ? null : (
        <Empty title="No readable series yet">
          <p>A project appears here automatically when it has Light Novel chapters.</p>
        </Empty>
      )}
    </>
  );
}
