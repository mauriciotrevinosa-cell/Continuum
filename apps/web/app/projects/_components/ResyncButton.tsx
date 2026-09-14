"use client";

import { useState } from "react";
import type { ProjectResync } from "@/lib/api";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../library/_vault/useAction";

/** Fetch the project's Git ref and re-read it at the commit it now points to. */
export function ResyncButton({ projectId, git }: { projectId: string; git: boolean }) {
  const { busy, error, run } = useAction();
  const [done, setDone] = useState<string | null>(null);
  return (
    <span className="row" style={{ gap: 8 }}>
      <button
        className="button small"
        type="button"
        disabled={busy}
        onClick={async () => {
          setDone(null);
          const result = await run(() =>
            vaultFetch<ProjectResync>(`projects/${encodeURIComponent(projectId)}/resync`, { json: {} }),
          );
          if (result) {
            const commit = result.commit ? result.commit.slice(0, 7) : "unknown";
            setDone(
              result.changed
                ? `Updated to ${commit}. ${result.detail}`
                : `Already at ${commit}. ${result.detail}`,
            );
          }
        }}
        title={git ? "Fetch the branch and re-read the committed documents" : "Re-read the project folder"}
      >
        {busy ? "Resyncing…" : git ? "Resync from Git" : "Re-read"}
      </button>
      <Feedback error={error} done={done} />
    </span>
  );
}
