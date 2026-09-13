"use client";

import { useActionState } from "react";
import type { ActionState } from "../actions";
import { ActionResult } from "./ActionResult";

/**
 * One button that runs one server action and says what happened.
 *
 * Every action here is read-only over the Vault by construction: the API
 * cannot pass --apply. The pending label is written for the person waiting,
 * not for a log.
 */
export function ActionButton({
  action,
  label,
  busyLabel,
  variant = "",
  quietResult = false,
}: {
  action: (previous: ActionState | null, form: FormData) => Promise<ActionState>;
  label: string;
  busyLabel: string;
  variant?: "" | "primary" | "small" | "primary small" | "ghost small";
  quietResult?: boolean;
}) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(action, null);
  return (
    <div>
      <form action={formAction}>
        <button className={`button ${variant}`} type="submit" disabled={pending} aria-live="polite">
          {pending ? <span className="spinner" aria-hidden /> : null}
          {pending ? busyLabel : label}
        </button>
      </form>
      {state && !(quietResult && state.ok) ? <ActionResult state={state} /> : null}
    </div>
  );
}
