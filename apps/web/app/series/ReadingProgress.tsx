"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { ReadingChapter } from "@/lib/series";

const key = (projectId: string) => `continuum:novel-progress:${projectId}`;
interface Progress { documentId: string; scrollY: number }

function read(projectId: string): Progress | null {
  try {
    const value = JSON.parse(localStorage.getItem(key(projectId)) ?? "null");
    return value && typeof value.documentId === "string" &&
      typeof value.scrollY === "number" && Number.isFinite(value.scrollY) && value.scrollY >= 0
      ? value : null;
  } catch { return null; }
}

export function ContinueReading({ projectId, chapters, firstDocumentId }: {
  projectId: string; chapters: ReadingChapter[]; firstDocumentId: string;
}) {
  const [saved, setSaved] = useState<ReadingChapter | null>(null);
  useEffect(() => {
    const progress = read(projectId);
    setSaved(chapters.find(chapter => chapter.documentId === progress?.documentId) ?? null);
  }, [projectId, chapters]);
  const target = saved?.documentId ?? firstDocumentId;
  return <Link className="button primary"
    href={`/series/${encodeURIComponent(projectId)}/chapters/${encodeURIComponent(target)}`}>
    {saved ? `Continue · Volume ${saved.volume}, Chapter ${saved.orderInVolume}` : "Start reading"}
  </Link>;
}

export function TrackReading({ projectId, documentId }: { projectId: string; documentId: string }) {
  useEffect(() => {
    const saved = read(projectId);
    const restore = saved?.documentId === documentId ? saved.scrollY : 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const save = () => {
      try { localStorage.setItem(key(projectId), JSON.stringify({ documentId, scrollY: window.scrollY })); }
      catch { /* Reading still works when browser storage is unavailable. */ }
    };
    const frame = requestAnimationFrame(() => { window.scrollTo(0, restore); save(); });
    const onScroll = () => { clearTimeout(timer); timer = setTimeout(save, 200); };
    window.addEventListener("scroll", onScroll);
    window.addEventListener("pagehide", save);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timer);
      save();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", save);
    };
  }, [projectId, documentId]);
  return null;
}
