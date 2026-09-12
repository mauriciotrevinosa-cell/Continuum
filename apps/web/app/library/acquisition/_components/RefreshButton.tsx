"use client";

import { useActionState } from "react";
import type { ActionState } from "../actions";
import { ActionResult } from "./ActionResult";

/**
 * Runs one read-only refresh (re-read the intake, recompute the scaffold
 * plan). Both are dry runs by construction: the API cannot pass --apply.
 */
export function RefreshButton({
  action,
  label,
  busyLabel,
  hint,
  compact = false,
}: {
  action: (previous: ActionState | null, form: FormData) => Promise<ActionState>;
  label: string;
  busyLabel: string;
  hint?: string;
  compact?: boolean;
}) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(action, null);
  return (
    <div>
      <form action={formAction} className="btn-row">
        <button className={`btn${compact ? " small" : ""}`} type="submit" disabled={pending}>
          {pending ? busyLabel : label}
        </button>
        {hint ? <span className="hint">{hint}</span> : null}
      </form>
      {state ? (
        <div style={{ marginTop: 10 }}>
          <ActionResult state={state} />
        </div>
      ) : null}
    </div>
  );
}
