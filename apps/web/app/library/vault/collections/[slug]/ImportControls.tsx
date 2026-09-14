"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../../../_vault/useAction";

/** Rescan, hash and import the collection - queued for the worker, repeat-safe. */
export function ImportControls({ slug, active }: { slug: string; active: boolean }) {
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
        disabled={busy || active}
        onClick={() =>
          run(
            () => vaultFetch(`catalog/collections/${slug}/import`, { method: "POST" }),
            "Import queued: the folder is rescanned, hashed, then imported. Files already imported are skipped.",
          )
        }
      >
        {active ? "Working…" : busy ? "Queuing…" : "Import collection"}
      </button>
      <Feedback error={error} done={done} />
    </div>
  );
}
