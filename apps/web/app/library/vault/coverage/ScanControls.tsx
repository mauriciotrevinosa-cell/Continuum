"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../_vault/useAction";

/**
 * Start a catalog scan (and the hash pass after it) for one folder or all.
 *
 * The API only queues the work; the worker scans. While anything is queued or
 * running, the page refreshes itself so progress shows without a reload.
 */
export function ScanControls({ rootKeys, active }: { rootKeys: string[]; active: boolean }) {
  const router = useRouter();
  const { busy, error, done, run } = useAction();

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => router.refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [active, router]);

  return (
    <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
      <button
        className="button primary"
        type="button"
        disabled={busy}
        onClick={() =>
          run(
            () => vaultFetch("catalog/scans", { json: { root_keys: rootKeys, hash: true } }),
            "Scan queued. The worker reads the folders; nothing in them is changed.",
          )
        }
      >
        {busy ? "Queuing…" : active ? "Scan again" : "Scan now"}
      </button>
      {active ? <span className="muted">Working… this page refreshes itself.</span> : null}
      <Feedback error={error} done={done} />
    </div>
  );
}
