"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { readProgress, resumeTarget } from "@/lib/reading-progress";

export interface ResumeChapter {
  documentId: string;
  title: string;
  volume: number;
  orderInVolume: number;
}

/**
 * The hero call to action: "Start reading" until there is a place to return to.
 *
 * Progress lives in the browser, which the server cannot see, so the first
 * paint is always the server's markup and the resume state arrives after
 * mount. Rendering the stored place straight away would be a hydration
 * mismatch.
 */
export function ResumeButton({
  projectId,
  chapters,
}: {
  projectId: string;
  chapters: ResumeChapter[];
}) {
  const [resume, setResume] = useState<{ chapter: ResumeChapter; midChapter: boolean } | null>(
    null,
  );
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const progress = readProgress(projectId);
    const order = chapters.map((chapter) => chapter.documentId);
    const target = resumeTarget(progress, order);
    if (!target) {
      setFinished(
        order.length > 0 && order.every((id) => progress.places[id]?.completed === true),
      );
      return;
    }
    const chapter = chapters.find((item) => item.documentId === target.documentId);
    if (chapter) setResume({ chapter, midChapter: target.midChapter });
  }, [projectId, chapters]);

  const first = chapters[0];
  const target = resume?.chapter ?? first;
  if (!target) return null;

  const href = `/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(target.documentId)}`;

  return (
    <Link className="button primary reading-resume" href={href}>
      <span className="reading-resume-label">
        {resume ? (resume.midChapter ? "Continue reading" : "Next chapter") : finished ? "Read again" : "Start reading"}
      </span>
      {resume ? (
        <span className="reading-resume-where">
          Volume {target.volume} · Chapter {target.orderInVolume} · {target.title}
        </span>
      ) : null}
    </Link>
  );
}
