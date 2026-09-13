import type { Readiness } from "@/lib/vault";

export const STATE_TONE: Record<string, string> = {
  APPROVED: "ok",
  GENERATED: "accent",
  QUEUED: "muted",
  RENDERING: "info",
  BLOCKED: "warn",
  FAILED: "err",
  REJECTED: "muted",
  SUPERSEDED: "muted",
};

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
        <strong>Deterministic sketch renderer.</strong> Attempts are labelled diagrams of the recipe -
        plate, edits, placements and bundle - not artwork. No image model is installed.
      </p>
    </div>
  ) : null;
}

