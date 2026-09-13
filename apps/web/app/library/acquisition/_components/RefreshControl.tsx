"use client";

import { useActionState } from "react";
import { refreshDataAction, type ActionState } from "../actions";

/**
 * Refresh means refresh: the engine walks the Vault again, rebuilds coverage
 * and the reports, and every screen re-reads them. Nothing restarts, nothing
 * in the Vault is written.
 */
export function RefreshControl({ variant = "small" }: { variant?: "small" | "primary" }) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(
    refreshDataAction,
    null,
  );
  const failed = state && !state.ok;
  return (
    <form action={formAction} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      {failed ? (
        <span className="muted" role="status" title={state.message}>
          Couldn&apos;t refresh
        </span>
      ) : state?.ok && !pending ? (
        <span className="muted" role="status">
          Refreshed
        </span>
      ) : null}
      <button
        className={`button ${variant === "primary" ? "primary" : "small"}`}
        type="submit"
        disabled={pending}
      >
        {pending ? <span className="spinner" aria-hidden /> : null}
        {pending ? "Reading your Vault…" : "Refresh"}
      </button>
    </form>
  );
}
