"use client";

import { useActionState } from "react";
import { type ActionState, addSourceAction, sourceAction } from "../actions";
import { ActionResult } from "./ActionResult";

/**
 * Add a web source. An address is enough; everything else is optional, and
 * what the source can actually do is discovered by testing it.
 *
 * Web addresses only. A folder on your own machine is registered with the
 * acquisition CLI, which writes the same registry this page reads, so the
 * browser never hands the API a filesystem path (F-50).
 */
export function AddSourceForm({ adapters }: { adapters: string[] }) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(
    addSourceAction,
    null,
  );
  return (
    <form className="form" action={formAction}>
      <div className="field">
        <label htmlFor="source-url">Website address</label>
        <input
          id="source-url"
          name="url"
          type="url"
          required
          inputMode="url"
          pattern="https?://.+"
          placeholder="https://publisher.example"
          autoComplete="off"
          aria-describedby="source-url-help"
        />
        <span className="help" id="source-url-help">
          A store, an official reader or a catalogue. Hosts on your never-use list are refused.
        </span>
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="source-name">Display name</label>
          <input id="source-name" name="name" type="text" autoComplete="off" placeholder="Optional" />
        </div>
        <div className="field">
          <label htmlFor="source-id">Id</label>
          <input
            id="source-id"
            name="source_id"
            type="text"
            pattern="[a-z0-9][a-z0-9_-]*"
            autoComplete="off"
            placeholder="Optional · lowercase"
          />
        </div>
        <div className="field">
          <label htmlFor="source-adapter">Kind</label>
          <select id="source-adapter" name="adapter" defaultValue="">
            <option value="">Detect automatically</option>
            {adapters.map((adapter) => (
              <option key={adapter} value={adapter}>
                {adapter === "web" ? "Website" : adapter === "bibliographic" ? "Catalogue" : adapter}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="form-row">
        <div className="field">
          <label htmlFor="source-search">Search address</label>
          <input
            id="source-search"
            name="search"
            type="text"
            placeholder="https://publisher.example/search?q={q}"
            autoComplete="off"
            aria-describedby="source-search-help"
          />
          <span className="help" id="source-search-help">
            Optional. Put <code>{"{q}"}</code> where the title goes.
          </span>
        </div>
        <div className="field">
          <label htmlFor="source-access">How it hands material over</label>
          <select id="source-access" name="access" defaultValue="">
            <option value="">Not sure yet</option>
            <option value="DRM_EBOOK">Buy the ebook (their app)</option>
            <option value="DRM_FREE_PURCHASE">Buy and download (DRM-free)</option>
            <option value="FREE_OFFICIAL_WEB">Free official reader</option>
            <option value="SUBSCRIPTION_WEB">Subscription reader</option>
            <option value="PAID_WEB">Pay per chapter</option>
            <option value="LIBRARY_LENDING">Library lending</option>
            <option value="STREAMING">Streaming</option>
            <option value="PHYSICAL_ONLY">Physical only</option>
          </select>
        </div>
      </div>
      <label className="check">
        <input type="checkbox" name="store_role" />
        Suggest this shop when a work has no known source
      </label>
      <label className="check">
        <input type="checkbox" name="download_permitted" />
        Files here are DRM-free and I am entitled to them
      </label>
      <label className="check">
        <input type="checkbox" name="skip_test" />
        Don&apos;t test the connection now
      </label>
      <div>
        <button className="button primary" type="submit" disabled={pending}>
          {pending ? <span className="spinner" aria-hidden /> : null}
          {pending ? "Adding…" : "Add source"}
        </button>
      </div>
      <ActionResult state={state} />
    </form>
  );
}

/** Test / enable / disable / remove one registered source. */
export function SourceRowActions({ id, name, enabled }: { id: string; name: string; enabled: boolean }) {
  const [state, formAction, pending] = useActionState<ActionState | null, FormData>(
    sourceAction,
    null,
  );
  return (
    <div style={{ display: "grid", justifyItems: "end", gap: 6 }}>
      <form action={formAction} className="chips">
        <input type="hidden" name="id" value={id} />
        <button className="button small" name="action" value="test" disabled={pending} aria-label={`Test ${name}`}>
          {pending ? "Working…" : "Test"}
        </button>
        <button
          className="button small"
          name="action"
          value={enabled ? "disable" : "enable"}
          disabled={pending}
          aria-label={`${enabled ? "Disable" : "Enable"} ${name}`}
        >
          {enabled ? "Disable" : "Enable"}
        </button>
        <button
          className="button small ghost danger"
          name="action"
          value="remove"
          disabled={pending}
          aria-label={`Remove ${name}`}
          onClick={(event) => {
            if (!window.confirm(`Remove "${name}" from your sources?`)) event.preventDefault();
          }}
        >
          Remove
        </button>
      </form>
      {state ? <ActionResult state={state} /> : null}
    </div>
  );
}
