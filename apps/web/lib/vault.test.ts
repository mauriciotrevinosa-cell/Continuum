import { describe, expect, it } from "vitest";
import { describeTally, intakeHint } from "./intake";
import { parseLinks } from "./links";
import { overlaps, regionFromPoints } from "./regions";
import { allowedVaultPath } from "./vault-paths";

const ID = "0190a5b2-1c3d-7e4f-8a9b-0c1d2e3f4a5b";

describe("allowedVaultPath", () => {
  it("allows the vault, inbox and production routes by id", () => {
    expect(allowedVaultPath(["library", "references", ID, "image"])).toBe(
      `library/references/${ID}/image`,
    );
    expect(allowedVaultPath(["library", "inbox", "files"])).toBe("library/inbox/files");
    expect(allowedVaultPath(["projects", "demo-saga", "rough-artifacts"])).toBe(
      "projects/demo-saga/rough-artifacts",
    );
    expect(allowedVaultPath(["production", "attempts", ID, "review"])).toBe(
      `production/attempts/${ID}/review`,
    );
  });

  it("refuses anything that could name a file or reach another route", () => {
    for (const segments of [
      [],
      ["library", "media", "m1_0123"],
      ["library", "references", "..", "..", "health"],
      ["library", "references", "C:", "ContinuumVault"],
      ["library", "references", "x%2F..%2Fy"],
      ["library", "references", ID, "image", "extra"],
      ["projects", "Demo Saga", "rough-artifacts"],
      ["jobs", ID, "cancel"],
      ["library", "inbox", "files\\..\\x"],
    ]) {
      expect(allowedVaultPath(segments)).toBeNull();
    }
  });
});

describe("regionFromPoints", () => {
  const box = { width: 200, height: 400 };

  it("normalizes a drag in any direction and clamps to the image", () => {
    expect(regionFromPoints({ x: 150, y: 300 }, { x: 50, y: 100 }, box)).toEqual({
      x: 0.25,
      y: 0.25,
      width: 0.5,
      height: 0.5,
    });
    expect(regionFromPoints({ x: -20, y: -20 }, { x: 400, y: 800 }, box)).toEqual({
      x: 0,
      y: 0,
      width: 1,
      height: 1,
    });
  });

  it("ignores a click that is not a selection", () => {
    expect(regionFromPoints({ x: 10, y: 10 }, { x: 11, y: 11 }, box)).toBeNull();
  });

  it("detects overlap but not touching edges", () => {
    const a = { x: 0, y: 0, width: 0.5, height: 0.5 };
    expect(overlaps(a, { x: 0.25, y: 0.25, width: 0.5, height: 0.5 })).toBe(true);
    expect(overlaps(a, { x: 0.5, y: 0, width: 0.5, height: 0.5 })).toBe(false);
  });
});

describe("parseLinks", () => {
  it("splits links, handles and tags even without line breaks", () => {
    expect(
      parseLinks("https://a.example/w/1 @artist #winter #outfithttps://b.example/w/2 #monster\nhttps://c.example/v/3"),
    ).toEqual([
      { url: "https://a.example/w/1", creator_handle: "@artist", tags: ["winter", "outfit"] },
      { url: "https://b.example/w/2", creator_handle: null, tags: ["monster"] },
      { url: "https://c.example/v/3", creator_handle: null, tags: [] },
    ]);
  });

  it("ignores text that is not a link", () => {
    expect(parseLinks("just some notes #tag @someone")).toEqual([]);
  });
});

describe("intakeHint", () => {
  it("counts extensions when the browser gives no type, and never guesses installers", () => {
    expect(intakeHint("artist_1_2_3.heic", "", false)).toBe("IMAGE");
    expect(intakeHint("PHOTO.HEIF", "", true)).toBe("SCREENSHOT");
    expect(intakeHint("reel.mp4", "", false)).toBe("VIDEO");
    expect(intakeHint("clip", "video/webm", false)).toBe("VIDEO");
    expect(intakeHint("Some Installer (1).exe", "application/x-msdownload", false)).toBeNull();
    expect(intakeHint("notes.txt", "text/plain", false)).toBeNull();
  });

  it("names every file that was not taken in", () => {
    expect(
      describeTally({ taken: 2, duplicates: ["a (1).jpg"], refused: [], skipped: ["setup.exe"] }),
    ).toBe(
      "2 taken in. 1 already in the inbox or library (a (1).jpg). 1 not images or clips, not sent (setup.exe).",
    );
  });
});
