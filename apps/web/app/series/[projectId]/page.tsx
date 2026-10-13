import Link from "next/link";
import { notFound } from "next/navigation";
import { loadReadableSeries } from "@/lib/series";
import { ReadingVolumes } from "./ReadingVolumes";
import { ResumeButton } from "./ResumeButton";

export const dynamic = "force-dynamic";

export default async function SeriesDetailPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  const series = await loadReadableSeries(projectId).catch(() => null);
  if (!series || !series.chapters.length) notFound();

  // Reading order across every volume: what "continue" walks forward through.
  const order = series.chapters.map((chapter) => ({
    documentId: chapter.documentId,
    title: chapter.title,
    volume: chapter.volume,
    orderInVolume: chapter.orderInVolume,
  }));

  return (
    <>
      <Link className="crumb" href="/series">
        ← Series
      </Link>

      <header className="reading-hero">
        <div>
          <p className="eyebrow">Light Novel · Season 1</p>
          <h1 className="title xl">{series.project.title}</h1>
          {series.project.logline ? <p className="reading-series-logline big">{series.project.logline}</p> : null}
          <p className="reading-summary">
            {series.volumes.length} volumes · {series.chapters.length} chapters · production draft
          </p>
        </div>
        <ResumeButton projectId={projectId} chapters={order} />
      </header>

      <ReadingVolumes projectId={projectId} volumes={series.volumes} />
    </>
  );
}
