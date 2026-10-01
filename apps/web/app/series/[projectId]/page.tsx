import Link from "next/link";
import { notFound } from "next/navigation";
import { loadReadableSeries } from "@/lib/series";

export const dynamic = "force-dynamic";

export default async function SeriesDetailPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const series = await loadReadableSeries(projectId).catch(() => null);
  if (!series || !series.chapters.length) notFound();

  const first = series.chapters[0];

  return (
    <>
      <Link className="crumb" href="/series">
        ← Series
      </Link>

      <header className="reading-hero">
        <div>
          <p className="eyebrow">Light Novel</p>
          <h1 className="title xl">{series.project.title}</h1>
          {series.project.logline ? <p className="reading-series-logline big">{series.project.logline}</p> : null}
          <p className="reading-summary">
            {series.volumes.length} volumes · {series.chapters.length} chapters · production draft
          </p>
        </div>
        <Link
          className="button primary"
          href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(first.documentId)}`}
        >
          Start reading
        </Link>
      </header>

      <div className="reading-volumes">
        {series.volumes.map((volume) => (
          <section className="reading-volume" key={volume.number}>
            <header>
              <div>
                <p className="eyebrow">{volume.season ? `Season ${volume.season} · ` : ""}Volume {volume.number}</p>
                <h2>Volume {volume.number}</h2>
              </div>
              <div className="reading-volume-meta">
                {volume.coverage ? <span>{volume.coverage}</span> : null}
                <span>{volume.chapters.length} chapters</span>
              </div>
            </header>

            <ol className="reading-chapter-list">
              {volume.chapters.map((chapter) => (
                <li key={chapter.documentId}>
                  <Link
                    href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(chapter.documentId)}`}
                  >
                    <span className="reading-chapter-number">{chapter.orderInVolume}</span>
                    <span className="reading-chapter-title">{chapter.title}</span>
                    <span className="reading-chapter-episode">{chapter.sourceEpisode}</span>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </>
  );
}
