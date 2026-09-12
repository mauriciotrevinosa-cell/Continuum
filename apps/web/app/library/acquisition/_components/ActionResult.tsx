"use client";

import type { ActionState } from "../actions";

/** Shows what an action did, including the exact command it ran. */
export function ActionResult({ state }: { state: ActionState | null }) {
  if (!state) return null;
  return (
    <div className={`result ${state.ok ? "ok" : "err"}`} role="status">
      <strong>{state.ok ? "Done." : "Not done."}</strong> {state.message}
      {state.command ? (
        <>
          <p className="row-meta" style={{ margin: "8px 0 4px" }}>
            Command:
          </p>
          <code className="cmd">{state.command}</code>
        </>
      ) : null}
      {state.output ? <pre>{state.output}</pre> : null}
    </div>
  );
}
