"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type SeriesProgress, readProgress, setChaptersRead } from "@/lib/reading-progress";

export interface ListChapter {
  documentId: string;
  title: string;
  sourceEpisode: string;
  orderInVolume: number;
  sameTime?: string;
}

/** "V16 #8–#23 (why)" -> "V16 #8–#23": the list has room for the range only. */
function sameTimeRange(note: string): string {
  return note.split(" (")[0];
}

/**
 * One volume's chapters, marked with what has been read.
 *
 * The list is identical to the server's markup until mount; the marks are
 * added afterwards from browser storage. A reader whose storage is blocked
 * simply sees an unmarked list, which is the list this page had before.
 */
export function ChapterList({
  projectId,
  chapters,
}: {
  projectId: string;
  chapters: ListChapter[];
}) {
  const [progress, setProgress] = useState<SeriesProgress | null>(null);

  useEffect(() => {
    setProgress(readProgress(projectId));
  }, [projectId]);

  const ids = chapters.map((chapter) => chapter.documentId);
  const allRead = progress !== null && ids.every((id) => progress.places[id]?.completed);

  function toggleVolume() {
    setChaptersRead(projectId, ids, !allRead);
    setProgress(readProgress(projectId));
  }

  return (
    <>
    <ol className="reading-chapter-list">
      {chapters.map((chapter) => {
        const place = progress?.places[chapter.documentId];
        const read = place?.completed === true;
        const started = !read && (place?.scroll ?? 0) > 0.02;
        return (
          <li key={chapter.documentId} data-read={read || undefined} data-started={started || undefined}>
            <Link
              href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(chapter.documentId)}`}
            >
              <span className="reading-chapter-number">{chapter.orderInVolume}</span>
              <span className="reading-chapter-title">
                {chapter.title}
                {chapter.sameTime ? (
                  <span className="reading-chapter-same-time" title={`Same time as ${chapter.sameTime}`}>
                    Same time as {sameTimeRange(chapter.sameTime)}
                  </span>
                ) : null}
                {read ? (
                  <span className="reading-chapter-check" role="img" aria-label="Read">
                    ✓
                  </span>
                ) : null}
              </span>
              <span className="reading-chapter-episode">
                {started ? `${Math.round((place?.scroll ?? 0) * 100)}%` : chapter.sourceEpisode}
              </span>
            </Link>
            {started ? (
              <span
                className="reading-chapter-bar"
                style={{ width: `${Math.round((place?.scroll ?? 0) * 100)}%` }}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
    {/* Only once storage has been read: before that the label would be a guess. */}
    {progress ? (
      <div className="reading-volume-actions">
        <button type="button" className="reading-volume-mark" onClick={toggleVolume}>
          {allRead ? "Mark volume unread" : "Mark volume read"}
        </button>
      </div>
    ) : null}
    </>
  );
}
