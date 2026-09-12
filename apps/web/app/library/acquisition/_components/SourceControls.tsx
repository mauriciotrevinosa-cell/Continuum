"use client";

import { useActionState } from "react";
import { type ActionState, addSourceAction, sourceAction } from "../actions";
import { ActionResult } from "./ActionResult";

/**
 * Add a source. The form stays deliberately small: a location is enough,
 * and everything else is optional. What the source can actually do is
 * discovered by testing it, not declared here.
 */
export function AddSourceForm({ adapters }: { adapters: string[] }) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(
    addSourceAction,
    null,
  );
  return (
    <form className="form" action={formAction}>
      <div className="form-grid">
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label htmlFor="source-url">Website URL or folder you own</label>
          <input
            id="source-url"
            name="url"
            type="text"
            required
            placeholder="https://publisher.example  —  or  D:\\My Purchases"
            autoComplete="off"
          />
          <span className="help">
            A store, an official reader, a catalogue, or a folder of files you already own. A host
            on your unofficial list is refused.
          </span>
        </div>
        <div className="field">
          <label htmlFor="source-name">Display name (optional)</label>
          <input id="source-name" name="name" type="text" autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor="source-id">Id (optional)</label>
          <input
            id="source-id"
            name="source_id"
            type="text"
            pattern="[a-z0-9][a-z0-9_-]*"
            autoComplete="off"
          />
          <span className="help">lowercase, no spaces</span>
        </div>
        <div className="field">
          <label htmlFor="source-adapter">Kind</label>
          <select id="source-adapter" name="adapter" defaultValue="">
            <option value="">detect automatically</option>
            {adapters.map((adapter) => (
              <option key={adapter} value={adapter}>
                {adapter}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label htmlFor="source-search">Search template (optional)</label>
          <input
            id="source-search"
            name="search"
            type="text"
            placeholder="https://publisher.example/search?q={q}"
            autoComplete="off"
          />
          <span className="help">
            Must contain <code>{"{q}"}</code>. Without it, a published OpenSearch document is used
            when the site has one.
          </span>
        </div>
      </div>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="source-access">How does it hand material over?</label>
          <select id="source-access" name="access" defaultValue="">
            <option value="">not sure yet</option>
            <option value="DRM_EBOOK">Buy the ebook (read in their app)</option>
            <option value="DRM_FREE_PURCHASE">Buy and download the file (DRM-free)</option>
            <option value="FREE_OFFICIAL_WEB">Free official reader</option>
            <option value="SUBSCRIPTION_WEB">Subscription reader</option>
            <option value="PAID_WEB">Pay per chapter</option>
            <option value="LIBRARY_LENDING">Library lending</option>
            <option value="STREAMING">Streaming</option>
            <option value="PHYSICAL_ONLY">Physical only</option>
          </select>
          <span className="help">Shown as a &quot;paid&quot; label before you click a search link.</span>
        </div>
        <div className="field">
          <label htmlFor="source-store">Offer it as a store</label>
          <label className="check" style={{ marginTop: 6 }}>
            <input id="source-store" type="checkbox" name="store_role" />
            Suggest this shop for English editions
          </label>
          <span className="help">Puts it among the fallbacks when a work has no known source.</span>
        </div>
      </div>
      <label className="check">
        <input type="checkbox" name="download_permitted" />
        Files here are DRM-free and I am entitled to them (allows automatic download)
      </label>
      <label className="check">
        <input type="checkbox" name="skip_test" />
        Skip the connection test (no network)
      </label>
      <div className="btn-row">
        <button className="btn primary" type="submit" disabled={pending}>
          {pending ? "Registering…" : "Add source"}
        </button>
      </div>
      <ActionResult state={state} />
    </form>
  );
}

/** Test / enable / disable / remove for one registered source. */
export function SourceRowActions({ id, enabled }: { id: string; enabled: boolean }) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(
    sourceAction,
    null,
  );
  return (
    <>
      <form action={formAction} className="btn-row">
        <input type="hidden" name="id" value={id} />
        <button className="btn small" name="action" value="test" disabled={pending}>
          {pending ? "Working…" : "Test"}
        </button>
        <button
          className="btn small"
          name="action"
          value={enabled ? "disable" : "enable"}
          disabled={pending}
        >
          {enabled ? "Disable" : "Enable"}
        </button>
        <button
          className="btn small danger"
          name="action"
          value="remove"
          disabled={pending}
          onClick={(event) => {
            if (!window.confirm(`Remove "${id}" from the registry?`)) event.preventDefault();
          }}
        >
          Remove
        </button>
      </form>
      {state ? (
        <div style={{ gridColumn: "1 / -1", marginTop: 10 }}>
          <ActionResult state={state} />
        </div>
      ) : null}
    </>
  );
}
