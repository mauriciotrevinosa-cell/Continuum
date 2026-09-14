import type { Readiness } from "@/lib/vault";

export const STATE_TONE: Record<string, string> = {
  TECHNICAL_PASS: "info",
  CREATIVE_APPROVED: "ok",
  FINAL_APPROVED: "ok",
  GENERATED: "accent",
  QUEUED: "muted",
  RENDERING: "info",
  BLOCKED: "warn",
  FAILED: "err",
  REJECTED: "muted",
  SUPERSEDED: "muted",
};

/** What each review state means, in words a reviewer reads. */
export const STATE_LABELS: Record<string, string> = {
  QUEUED: "Queued",
  RENDERING: "Rendering",
  GENERATED: "Generated · needs review",
  TECHNICAL_PASS: "Technical pass · workflow verified",
  CREATIVE_APPROVED: "Creative approved",
  FINAL_APPROVED: "Final approved",
  REJECTED: "Rejected",
  SUPERSEDED: "Superseded",
  BLOCKED: "Blocked",
  FAILED: "Failed",
  PAUSED: "Paused",
  CANCELLED: "Cancelled",
};

export const DECISION_LABELS: Record<string, string> = {
  TECHNICAL_PASS: "Technical pass",
  CREATIVE_APPROVE: "Creative approve",
  FINAL_APPROVE: "Final approve",
  REJECT: "Reject",
  REGENERATE: "Regenerate",
};

export const PURPOSE_LABELS: Record<string, string> = {
  PRODUCTION: "Production",
  WORKFLOW_TEST: "Workflow test · non-canon",
  NON_CANON_SAMPLE: "Non-canon sample",
};

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

/** TEST ONLY: shown wherever a test artifact or test render could be mistaken for manga. */
export function TestOnlyChip({ purpose, output }: { purpose?: string; output?: string | null }) {
  if (purpose && purpose !== "PRODUCTION") {
    return (
      <span className="chip warn" title="Never manga, never counted toward completion, never creatively approved.">
        TEST ONLY · {PURPOSE_LABELS[purpose] ?? purpose}
      </span>
    );
  }
  if (output === "TEST_RENDER") {
    return (
      <span className="chip warn" title="Drawn by the test renderer: a labelled diagram of the recipe, not artwork.">
        TEST RENDER
      </span>
    );
  }
  return null;
}

/** Says plainly which renderer will draw attempts - or that none may. */
export function ReadinessBanner({ readiness }: { readiness: Readiness | null }) {
  if (!readiness) return null;
  if (!readiness.permitted) {
    return (
      <div className="banner err">
        <p>
          <strong>No rough renderer is permitted.</strong>{" "}
          {String(readiness.remediation?.message ?? "Attempts will wait as blocked until one is.")}
        </p>
      </div>
    );
  }
  return readiness.is_fake ? (
    <div className="banner">
      <p>
        <strong>Deterministic sketch renderer (test renderer).</strong> Attempts are labelled diagrams
        of the recipe - plate, edits, placements and bundle - not artwork, so they can pass technically
        but can never be creatively approved. No image model is installed.
      </p>
    </div>
  ) : null;
}

