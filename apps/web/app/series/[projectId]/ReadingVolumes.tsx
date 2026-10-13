"use client";

import { type SyntheticEvent, useEffect, useState } from "react";
import { type SeriesProgress, readProgress } from "@/lib/reading-progress";
import type { ReadingVolume } from "@/lib/series";
import { ChapterList } from "./ChapterList";

/**
 * Every volume, with the ones already read folded out of the way.
 *
 * A volume counts as read when all of its chapters are marked read, or when
 * the reader's last chapter is in a later volume: a chapter skipped long ago
 * should not keep a finished volume open forever. The unbroken run of read
 * volumes at the start collapses further, into one row, because twenty
 * folded volumes are still twenty rows to scroll past.
 *
 * Folding is decided once, after mount, from browser storage, so the first
 * paint matches the server's markup (everything open). After that the
 * reader's own clicks win; marking a volume read does not snap it shut
 * under their cursor.
 */
export function ReadingVolumes({ projectId, volumes }: { projectId: string; volumes: ReadingVolume[] }) {
  const [progress, setProgress] = useState<SeriesProgress | null>(null);
  const [toggled, setToggled] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setProgress(readProgress(projectId));
  }, [projectId]);

  const lastVolume = progress?.lastDocumentId
    ? (volumes.find((volume) => volume.chapters.some((chapter) => chapter.documentId === progress.lastDocumentId))
        ?.number ?? null)
    : null;

  function isRead(volume: ReadingVolume): boolean {
    if (!progress) return false;
    const allDone =
      volume.chapters.length > 0 &&
      volume.chapters.every((chapter) => progress.places[chapter.documentId]?.completed === true);
    return allDone || (lastVolume !== null && volume.number < lastVolume);
  }

  function foldProps(key: string, defaultOpen: boolean) {
    const open = toggled[key] ?? defaultOpen;
    return {
      open,
      onToggle: (event: SyntheticEvent<HTMLDetailsElement>) => {
        const nowOpen = event.currentTarget.open;
        if (nowOpen !== open) setToggled((prev) => ({ ...prev, [key]: nowOpen }));
      },
    };
  }

  function renderVolume(volume: ReadingVolume) {
    const read = isRead(volume);
    return (
      <details
        className="reading-volume"
        id={`volume-${volume.number}`}
        key={volume.number}
        {...foldProps(`v${volume.number}`, !read)}
      >
        <summary>
          <div>
            <p className="eyebrow">Volume {volume.number}</p>
            <h2>Volume {volume.number}</h2>
          </div>
          <div className="reading-volume-meta">
            {read ? <span className="reading-volume-read">✓ Read</span> : null}
            {volume.coverage ? <span>{volume.coverage}</span> : null}
            <span>{volume.chapters.length} chapters</span>
          </div>
        </summary>

        <ChapterList projectId={projectId} chapters={volume.chapters} />
      </details>
    );
  }

  let leadingRead = 0;
  while (leadingRead < volumes.length && isRead(volumes[leadingRead])) leadingRead += 1;
  const shelved = leadingRead >= 2 ? volumes.slice(0, leadingRead) : [];
  const rest = shelved.length ? volumes.slice(leadingRead) : volumes;
  const shelvedChapters = shelved.reduce((sum, volume) => sum + volume.chapters.length, 0);

  return (
    <div className="reading-volumes">
      {shelved.length ? (
        <details className="reading-volume reading-volume-shelf" {...foldProps("shelf", false)}>
          <summary>
            <div>
              <h2>
                Volumes {shelved[0].number}–{shelved[shelved.length - 1].number}
              </h2>
            </div>
            <div className="reading-volume-meta">
              <span className="reading-volume-read">✓ Read</span>
              <span>{shelvedChapters} chapters</span>
            </div>
          </summary>
          <div className="reading-volume-shelf-list">{shelved.map(renderVolume)}</div>
        </details>
      ) : null}
      {rest.map(renderVolume)}
    </div>
  );
}
