import Link from "next/link";
import { notFound } from "next/navigation";
import { projects } from "@/lib/api";
import { loadReadableSeries, manuscriptForReading } from "@/lib/series";
import { Markdown } from "@/app/projects/_components/Markdown";
import { ChapterProgress, NextChapterLink } from "./ChapterProgress";

export const dynamic = "force-dynamic";

export default async function SeriesChapterPage({
  params,
}: {
  params: Promise<{ projectId: string; documentId: string }>;
}) {
  const { projectId, documentId } = await params;
  const series = await loadReadableSeries(projectId).catch(() => null);
  if (!series) notFound();

  const index = series.chapters.findIndex((chapter) => chapter.documentId === documentId);
  if (index < 0) notFound();

  const chapter = series.chapters[index];
  const previous = index > 0 ? series.chapters[index - 1] : null;
  const next = index + 1 < series.chapters.length ? series.chapters[index + 1] : null;
  const volume = series.volumes.find((item) => item.number === chapter.volume);
  if (!volume) notFound();
  const body = await projects.document(projectId, documentId).catch(() => null);
  if (!body) notFound();

  const source = manuscriptForReading(body.markdown);

  return (
    <div className="novel-reader">
      <ChapterProgress projectId={projectId} documentId={documentId} />
      <nav className="novel-reader-top" aria-label="Chapter navigation">
        <Link href={`/series/${encodeURIComponent(projectId)}`}>← Contents</Link>
        <span>
          Volume {chapter.volume} · Chapter {chapter.orderInVolume} of {volume.chapters.length}
        </span>
        <Link
          className="novel-reader-source"
          href={`/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`}
        >
          Production source
        </Link>
      </nav>

      <article className="novel-reader-page">
        <header className="novel-reader-head">
          <p className="eyebrow">
            Volume {chapter.volume} · {chapter.sourceEpisode}
          </p>
          <h1>{chapter.title}</h1>
          {chapter.sameTime ? <p className="novel-reader-same-time">Same time as {chapter.sameTime}</p> : null}
        </header>

        <div className="novel-reader-copy">
          <Markdown source={source} />
        </div>
      </article>

      <nav className="novel-reader-pager" aria-label="Previous and next chapters">
        {previous ? (
          <Link
            className="novel-reader-nav-card"
            href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(previous.documentId)}`}
          >
            <span>← Previous</span>
            <strong>{previous.title}</strong>
          </Link>
        ) : (
          <span />
        )}

        {next ? (
          <NextChapterLink
            projectId={projectId}
            documentId={documentId}
            className="novel-reader-nav-card next"
            href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(next.documentId)}`}
          >
            <span>Next →</span>
            <strong>{next.title}</strong>
          </NextChapterLink>
        ) : (
          <NextChapterLink
            projectId={projectId}
            documentId={documentId}
            className="novel-reader-nav-card next"
            href={`/series/${encodeURIComponent(projectId)}`}
          >
            <span>Finished Season 1</span>
            <strong>Back to contents</strong>
          </NextChapterLink>
        )}
      </nav>
    </div>
  );
}
