import { describe, expect, it } from "vitest";
import type { ProjectDocument } from "./api";
import { parseVolume } from "./series";
const doc = (id: string, episode: string, volume: number, order: number, title: string) => ({
  title, section: "production", lifecycle: "DRAFT", version: "0.1", lineage: id,
  supersedes: null, superseded_by: null, derived_from: null, summary: "", author_status: null,
  dated: null, modified_at: null, size_bytes: 0, filed: true, constraints: [], maturity: null,
  authority: "CONTENT", overrides: [], overridden_by: [], registration: "convention",
  convention: "episode-ln-chapter", commit: null, resolved_by: null, applies_to: null,
  id, episode, category: "ln-chapter", facts: { volume: String(volume), reading_order: String(order), chapter_title: title },
}) satisfies ProjectDocument;

describe("reader volume indexes", () => {
  it("resolves title-only rows by volume, reading order and title, not document position", () => {
    const documents = [doc("s4e17-ln-chapter-02", "S4E17", 23, 2, "The Gate"), doc("s4e17-ln-chapter-01", "S4E17", 23, 1, "The Coin That Stayed"), doc("other-ln-chapter-01", "S3E1", 10, 1, "The Coin That Stayed")];
    const parsed = parseVolume("**Volume:** 23\r\n**Season:** 4\r\n| # | Chapter |\r\n|---:|---|\r\n| 1 | The Coin That Stayed |\r\n| 2 | The Gate |\r\n", documents)!;
    expect(parsed.chapters.map(c => c.documentId)).toEqual(["s4e17-ln-chapter-01", "s4e17-ln-chapter-02"]);
    expect(parsed.chapters[0].sourceEpisode).toBe("S4E17");
  });
  it("preserves episode-only and explicit-file indexes", () => {
    const documents = [doc("s1e1-ln-chapter-01", "S1E1", 1, 1, "The Shot")];
    for (const row of ["| 1 | S1E1 | The Shot |", "| 1 | S1E1 | The Shot | `THE_ARRIVALS_S1E1_LN_CHAPTER_01_THE_SHOT_v0.1.md` |"])
      expect(parseVolume(`**Volume:** 1\n${row}`, documents)!.chapters[0].documentId).toBe(documents[0].id);
  });
  it("does not silently hide a chapter or guess its identity", () => {
    expect(() => parseVolume("**Volume:** 23\n| 1 | Wrong Title |", [doc("s4e17-ln-chapter-01", "S4E17", 23, 1, "The Coin That Stayed")])).toThrow("unresolved index entry");
  });
});
