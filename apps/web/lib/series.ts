import { cache } from "react";
import {
  type ProjectDetail,
  type ProjectDocument,
  type ProjectSummary,
  projects,
} from "./api";

export interface ReadingChapter {
  documentId: string;
  title: string;
  sourceEpisode: string;
  sourceFile: string;
  volume: number;
  orderInVolume: number;
  globalOrder: number;
}

export interface ReadingVolume {
  number: number;
  coverage: string | null;
  chapters: ReadingChapter[];
}

export interface ReadableSeries {
  project: ProjectSummary;
  volumes: ReadingVolume[];
  chapters: ReadingChapter[];
}

export interface ReadableSeriesSummary {
  project: ProjectSummary;
  chapters: number;
  volumes: number;
}

const FIELD = (name: string) =>
  new RegExp(
    `^\\*\\*${name.replace(/[.*+?^$\\{\\}()|[\\]\\\\]/g, "\\$&")}:\\*\\*\\s*(.+?)\\s*$`,
    "mi",
  );

function readField(markdown: string, name: string): string | null {
  return FIELD(name).exec(markdown)?.[1]?.trim() ?? null;
}

function chapterDocument(
  documents: ProjectDocument[],
  sourceEpisode: string,
  fileName: string,
): ProjectDocument | null {
  const file = /_(S\d+E\d+)_LN_CHAPTER_(\d+)_/i.exec(fileName);
  const chapter = file?.[2];
  if (!chapter) return null;
  const suffix = `-ln-chapter-${chapter}`;
  return (
    documents.find(
      (document) =>
        document.category === "ln-chapter" &&
        document.episode?.toUpperCase() === sourceEpisode.toUpperCase() &&
        document.id.endsWith(suffix),
    ) ?? null
  );
}

function parseVolume(
  markdown: string,
  documents: ProjectDocument[],
): Omit<ReadingVolume, "chapters"> & { chapters: Omit<ReadingChapter, "globalOrder">[] } | null {
  const number = Number.parseInt(readField(markdown, "Volume") ?? "", 10);
  if (!Number.isFinite(number)) return null;

  const coverage = readField(markdown, "Coverage");
  const chapters: Omit<ReadingChapter, "globalOrder">[] = [];
  const row =
    /^\|\s*(\d+)\s*\|\s*(S\d+E\d+)\s*\|\s*(.*?)\s*\|\s*`([^`]+)`\s*\|\s*$/gim;

  for (const match of markdown.matchAll(row)) {
    const orderInVolume = Number.parseInt(match[1], 10);
    const sourceEpisode = match[2].toUpperCase();
    const title = match[3].trim();
    const sourceFile = match[4].trim();
    const document = chapterDocument(documents, sourceEpisode, sourceFile);
    if (!document) continue;
    chapters.push({
      documentId: document.id,
      title,
      sourceEpisode,
      sourceFile,
      volume: number,
      orderInVolume,
    });
  }

  chapters.sort((a, b) => a.orderInVolume - b.orderInVolume);
  return { number, coverage, chapters };
}

function documentSortKey(document: ProjectDocument): [number, number, number] {
  const episode = /^S(\d+)E(\d+)$/i.exec(document.episode ?? "");
  const chapter = /-ln-chapter-(\d+)$/i.exec(document.id);
  return [
    Number.parseInt(episode?.[1] ?? "999", 10),
    Number.parseInt(episode?.[2] ?? "999", 10),
    Number.parseInt(chapter?.[1] ?? "999", 10),
  ];
}

function compareDocuments(a: ProjectDocument, b: ProjectDocument): number {
  const aa = documentSortKey(a);
  const bb = documentSortKey(b);
  return aa[0] - bb[0] || aa[1] - bb[1] || aa[2] - bb[2];
}

function fallbackVolume(detail: ProjectDetail): ReadingVolume[] {
  const chapters = detail.documents
    .filter((document) => document.category === "ln-chapter")
    .sort(compareDocuments)
    .map((document, index) => ({
      documentId: document.id,
      title: document.title,
      sourceEpisode: document.episode ?? "",
      sourceFile: "",
      volume: 1,
      orderInVolume: index + 1,
      globalOrder: index + 1,
    }));

  return chapters.length ? [{ number: 1, coverage: null, chapters }] : [];
}

export const loadReadableSeries = cache(async (projectId: string): Promise<ReadableSeries> => {
  const detail = await projects.detail(projectId);
  const indexes = detail.documents
    .filter((document) => document.category === "ln-volume")
    .sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));

  const parsed = await Promise.all(
    indexes.map(async (index) => {
      const body = await projects.document(projectId, index.id);
      return parseVolume(body.markdown, detail.documents);
    }),
  );

  const usable = parsed
    .filter((volume): volume is NonNullable<typeof volume> => Boolean(volume))
    .filter((volume) => volume.chapters.length)
    .sort((a, b) => a.number - b.number);

  const volumes: ReadingVolume[] = [];
  let globalOrder = 1;
  for (const volume of usable) {
    volumes.push({
      number: volume.number,
      coverage: volume.coverage,
      chapters: volume.chapters.map((chapter) => ({ ...chapter, globalOrder: globalOrder++ })),
    });
  }

  const resolvedVolumes = volumes.length ? volumes : fallbackVolume(detail);
  return {
    project: detail.project,
    volumes: resolvedVolumes,
    chapters: resolvedVolumes.flatMap((volume) => volume.chapters),
  };
});

export async function listReadableSeries(): Promise<ReadableSeriesSummary[]> {
  const all = await projects.list();
  const details = await Promise.all(
    all.map(async (project) => {
      try {
        const detail = await projects.detail(project.id);
        const chapters = detail.documents.filter((document) => document.category === "ln-chapter").length;
        const volumes = detail.documents.filter((document) => document.category === "ln-volume").length;
        return chapters ? { project, chapters, volumes } : null;
      } catch {
        return null;
      }
    }),
  );
  return details.filter((item): item is ReadableSeriesSummary => Boolean(item));
}

export function manuscriptForReading(markdown: string): string {
  let source = markdown.replace(/\r\n?/g, "\n");

  source = source.replace(/<!--[^]*?-->/g, "");

  const lines = source.split("\n");
  while (lines.length && !lines[0].trim()) lines.shift();

  if (lines[0]?.startsWith("# ")) lines.shift();
  while (lines.length && !lines[0].trim()) lines.shift();

  if (/^##\s+Chapter\b/i.test(lines[0] ?? "")) lines.shift();
  while (lines.length && !lines[0].trim()) lines.shift();

  while (/^\*\*[^*]{1,80}:\*\*/.test(lines[0] ?? "")) {
    lines.shift();
  }
  while (lines.length && !lines[0].trim()) lines.shift();

  return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}
