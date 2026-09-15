import { describe, expect, it } from "vitest";
import { type PageSummary, approvalDecision, pageBlocker, vaultImage } from "./manga";

const page = (sequence: number, state: PageSummary["state"], reasons: PageSummary["reasons"] = []): PageSummary => ({
  id: `p${sequence}`,
  sequence,
  page_key: `demo-c1-s00${sequence}`,
  integrated_page: 40 + sequence,
  label: null,
  state,
  reasons,
  approved_attempt_id: null,
  latest_attempt_id: null,
  attempt_count: 0,
  images: null,
});

describe("page production helpers", () => {
  it("says which page a waiting page waits for", () => {
    const pages = [page(1, "IN_REVIEW"), page(2, "WAITING")];
    expect(pageBlocker(pages[1], pages)).toBe("Waiting for page 1 (p. 41) to be approved.");
    expect(pageBlocker(pages[0], pages)).toBeNull();
  });

  it("explains a blocked page by its missing references", () => {
    const blocked = page(1, "BLOCKED", [
      { kind: "MISSING_REQUIRED_REFERENCE", key: "Aster Vale", detail: "Aster Vale lacks grounded body" },
    ]);
    expect(pageBlocker(blocked, [blocked])).toBe("Missing required references: Aster Vale lacks grounded body");
  });

  it("approves a sample page with a technical pass and canon with creative approval", () => {
    expect(approvalDecision("NON_CANON_SAMPLE")).toBe("TECHNICAL_PASS");
    expect(approvalDecision("PRODUCTION")).toBe("CREATIVE_APPROVE");
  });

  it("routes API image paths through the same-origin passage", () => {
    expect(vaultImage("/production/attempts/x/image?kind=BW_FINISH")).toBe(
      "/vault-api/production/attempts/x/image?kind=BW_FINISH",
    );
  });
});
