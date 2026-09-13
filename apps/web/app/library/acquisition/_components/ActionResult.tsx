"use client";

import type { ActionState } from "../actions";

/**
 * What an action did, in a sentence. The exact command and its output are
 * one click further: always available, never in the way.
 */
export function ActionResult({ state }: { state: ActionState | null }) {
  if (!state) return null;
  return (
    <div className={`result ${state.ok ? "ok" : "err"}`} role="status">
      <span>{state.message}</span>
      {state.command || state.output ? (
        <details className="disclosure" style={{ marginTop: 8 }}>
          <summary>Technical details</summary>
          <div className="disclosure-body">
            {state.command ? <code className="cmd">{state.command}</code> : null}
            {state.output ? <pre>{state.output}</pre> : null}
          </div>
        </details>
      ) : null}
    </div>
  );
}
