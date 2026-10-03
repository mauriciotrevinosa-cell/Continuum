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
  season: number | null;
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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const FIELD = (name: string) =>
  new RegExp("^\\*\\*" + escapeRegExp(name) + ":\\*\\*\\s*(.+?)\\s*$", "mi");

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

/** `| 3 | S3E1 | Tomorrow Is Terrain | `<chapter file>.md` |` */
const ROW_WITH_FILE =
  /^\|\s*(\d+)\s*\|\s*(S\d+E\d+)\s*\|\s*(.*?)\s*\|\s*`([^`]+)`\s*\|\s*$/gim;
/** `| 3 | S3E7 | No One Waits |` - the later volumes dropped the File column. */
const ROW_PLAIN = /^\|\s*(\d+)\s*\|\s*(S\d+E\d+)\s*\|\s*([^|]*?)\s*\|\s*$/gim;

/** The `nth` chapter document of an episode, counting from 1 in chapter order. */
function nthChapterOf(
  documents: ProjectDocument[],
  episode: string,
  nth: number,
): ProjectDocument | null {
  const ofEpisode = documents
    .filter(
      (document) =>
        document.category === "ln-chapter" &&
        document.episode?.toUpperCase() === episode.toUpperCase(),
    )
    .sort((a, b) => {
      const an = Number.parseInt(/-ln-chapter-(\d+)$/i.exec(a.id)?.[1] ?? "999", 10);
      const bn = Number.parseInt(/-ln-chapter-(\d+)$/i.exec(b.id)?.[1] ?? "999", 10);
      return an - bn;
    });
  return ofEpisode[nth - 1] ?? null;
}

/**
 * This volume's chapters in order, from either shape of index table.
 *
 * The File column is a convenience, not the identity: a chapter document is
 * `<episode>-ln-chapter-NN`, and a volume covers whole episodes, so the rows of
 * one episode map onto that episode's chapters in order. Volumes 11 and up were
 * written without the File column and used to vanish from the reader entirely -
 * the volume parsed, matched no chapter, and was dropped for being empty.
 */
function parseVolume(
  markdown: string,
  documents: ProjectDocument[],
): Omit<ReadingVolume, "chapters"> & { chapters: Omit<ReadingChapter, "globalOrder">[] } | null {
  const number = Number.parseInt(readField(markdown, "Volume") ?? "", 10);
  if (!Number.isFinite(number)) return null;

  const seasonValue = Number.parseInt(readField(markdown, "Season") ?? "", 10);
  const season = Number.isFinite(seasonValue) ? seasonValue : null;
  const coverage = readField(markdown, "Coverage");
  const chapters: Omit<ReadingChapter, "globalOrder">[] = [];

  const withFile = [...markdown.matchAll(ROW_WITH_FILE)];
  const rows = withFile.length
    ? withFile.map((m) => ({
        order: Number.parseInt(m[1], 10),
        episode: m[2].toUpperCase(),
        title: m[3].trim(),
        file: m[4].trim(),
      }))
    : [...markdown.matchAll(ROW_PLAIN)].map((m) => ({
        order: Number.parseInt(m[1], 10),
        episode: m[2].toUpperCase(),
        title: m[3].trim(),
        file: "",
      }));

  // How many rows of each episode have been placed, so the next one takes that
  // episode's next chapter.
  const taken = new Map<string, number>();

  for (const row of rows) {
    const document = row.file
      ? chapterDocument(documents, row.episode, row.file)
      : nthChapterOf(documents, row.episode, (taken.get(row.episode) ?? 0) + 1);
    taken.set(row.episode, (taken.get(row.episode) ?? 0) + 1);
    if (!document) continue;
    chapters.push({
      documentId: document.id,
      title: row.title,
      sourceEpisode: row.episode,
      sourceFile: row.file,
      volume: number,
      orderInVolume: row.order,
    });
  }

  chapters.sort((a, b) => a.orderInVolume - b.orderInVolume);
  return { number, season, coverage, chapters };
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

  return chapters.length ? [{ number: 1, season: null, coverage: null, chapters }] : [];
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
      season: volume.season,
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
