"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { MemberState } from "@/lib/catalog";
import { formatBytes } from "@/lib/acquisition";
import { vaultFetch } from "@/lib/vault";
import { Player } from "../../view/Player";

/**
 * A video that lives inside a compressed archive.
 *
 * It cannot be streamed from inside the archive, so the worker copies this one
 * episode, verified, into Continuum's bounded cache first. The archive in the
 * Vault is only read; the cached copy is evicted when space is needed.
 */
export function MemberWatch({ initial }: { initial: MemberState }) {
  const router = useRouter();
  const [state, setState] = useState(initial);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (state.state !== "preparing") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await vaultFetch<MemberState>(`catalog/members/${state.member_id}`);
        setState(next);
        if (next.state === "ready") router.refresh();
      } catch (cause) {
        setError(String(cause));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [state.state, state.member_id, router]);

  const prepare = async () => {
    setError(null);
    try {
      setState(await vaultFetch<MemberState>(`catalog/members/${state.member_id}/prepare`, { method: "POST" }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  if (state.state === "ready") {
    return <Player source={{ kind: "member", memberId: state.member_id }} maybe={state.plays_in_browser === "maybe"} />;
  }
  return (
    <section className="surface" style={{ padding: "22px 24px" }}>
      <p style={{ marginTop: 0 }}>
        <strong>This episode is inside a compressed archive</strong> ({state.archive}). To play it,
        Continuum copies just this video ({formatBytes(state.byte_size)}) into its own cache. Your Vault
        is not changed.
      </p>
      {state.state === "preparing" ? (
        <p className="muted" role="status">
          Preparing… the worker is extracting and verifying it{state.job_status ? ` (${state.job_status.toLowerCase()})` : ""}.
        </p>
      ) : state.state === "unavailable" ? (
        <p className="error-text" role="alert">
          {state.detail || "This video could not be prepared."} Rescan the Vault from Coverage, then try again.
        </p>
      ) : null}
      {state.state !== "preparing" ? (
        <button className="button primary" type="button" onClick={prepare}>
          {state.state === "unavailable" ? "Try again" : "Prepare to watch"}
        </button>
      ) : null}
      {error ? (
        <p className="error-text" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
