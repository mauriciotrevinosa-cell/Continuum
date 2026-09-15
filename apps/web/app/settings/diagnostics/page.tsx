import Link from "next/link";
import { API_BASE, ApiUnreachableError, type AcquisitionStatus, acquisition } from "@/lib/api";
import { formatBytes, formatWhen, plural, timeAgo } from "@/lib/acquisition";
import { type Backend, manga } from "@/lib/manga";
import { RefreshControl } from "../../library/acquisition/_components/RefreshControl";
import { BackendList } from "../../production/_parts/manga";

export const dynamic = "force-dynamic";

/**
 * Where the Library's data comes from, for the rare moment it matters.
 *
 * Paths, commands and document timestamps live here so that no everyday
 * screen has to carry them.
 */
export default async function DiagnosticsPage() {
  let status: AcquisitionStatus | null = null;
  let error: string | null = null;
  const started = Date.now();
  try {
    status = await acquisition.status();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const latency = Date.now() - started;
  const backends: Backend[] | null = await manga.backends().catch(() => null);
  const fresh = status?.freshness;

  return (
    <>
      <header className="page-head">
        <div>
          <p className="eyebrow">Settings</p>
          <h1 className="title">Diagnostics</h1>
          <p className="lead">Where the Library&apos;s data comes from, and how current it is.</p>
        </div>
        {status?.cli_available ? <RefreshControl variant="primary" /> : null}
      </header>

      <section aria-labelledby="artwork" style={{ marginBottom: 28 }}>
        <div className="block-head">
          <h2 id="artwork">Artwork backends</h2>
        </div>
        {backends ? (
          <BackendList backends={backends} />
        ) : (
          <p className="hint">The API did not report artwork backends.</p>
        )}
        <p className="hint">
          ComfyUI backends are registered only when configured (CONTINUUM_COMFY_LOCAL_URL, CONTINUUM_COMFY_REMOTE_URL and
          the checkpoint record). No paid service is ever enabled.
        </p>
      </section>

      <section aria-labelledby="service">
        <div className="block-head">
          <h2 id="service">Library service</h2>
        </div>
        <dl className="kv surface">
          <dt>API</dt>
          <dd>
            {error ? (
              <span className="chip err">Unreachable</span>
            ) : (
              <span className="chip ok">Connected · {latency} ms</span>
            )}{" "}
            <code>{API_BASE}</code>
          </dd>
          {error ? (
            <>
              <dt>Error</dt>
              <dd>
                <code>{error}</code>
              </dd>
            </>
          ) : null}
          {status ? (
            <>
              <dt>Acquisition tool</dt>
              <dd>
                {status.cli_available ? (
                  <span className="chip ok">Configured</span>
                ) : (
                  <span className="chip muted">Not configured - screens are read-only</span>
                )}{" "}
                {status.cli_path ? <code>{status.cli_path}</code> : null}
              </dd>
              <dt>Data directory</dt>
              <dd>
                <code>{status.data_dir || "(not configured)"}</code>
                {status.available ? "" : " · does not exist yet"}
              </dd>
              <dt>Vault</dt>
              <dd>
                <code>{status.vault_root || "(unknown until the first scan)"}</code>{" "}
                <span className="muted">· read-only to Continuum</span>
              </dd>
              <dt>Library size</dt>
              <dd>
                {plural(status.library_files, "file")} · {formatBytes(status.library_bytes)}
              </dd>
            </>
          ) : null}
        </dl>
      </section>

      {fresh ? (
        <section className="block" aria-labelledby="freshness">
          <div className="block-head">
            <h2 id="freshness">Freshness</h2>
          </div>
          <dl className="kv surface">
            <dt>State</dt>
            <dd>
              <span className={`chip ${fresh.state === "fresh" ? "ok" : fresh.state === "stale" ? "info" : "muted"}`}>
                {fresh.state === "fresh"
                  ? "Up to date with the Vault"
                  : fresh.state === "stale"
                    ? "The Vault changed after the last scan"
                    : fresh.state === "empty"
                      ? "No scan yet"
                      : "Could not check the Vault"}
              </span>
              {fresh.detail ? <span className="muted"> · {fresh.detail}</span> : null}
            </dd>
            <dt>Last library scan</dt>
            <dd>
              {formatWhen(fresh.library_scanned_at)}{" "}
              <span className="muted">({timeAgo(fresh.library_scanned_at)})</span>
            </dd>
            <dt>Last catalogue refresh</dt>
            <dd>
              {formatWhen(fresh.catalogue_refreshed_at)}{" "}
              <span className="muted">({timeAgo(fresh.catalogue_refreshed_at)})</span>
            </dd>
            <dt>Documents written</dt>
            <dd>{formatWhen(fresh.documents_generated_at)}</dd>
            {fresh.changed_families.length || fresh.changed_folders.length ? (
              <>
                <dt>Changed since scan</dt>
                <dd>{[...fresh.changed_families, ...fresh.changed_folders].join(" · ")}</dd>
              </>
            ) : null}
            <dt>Duplicate check</dt>
            <dd>
              {fresh.unhashed_files
                ? `${plural(fresh.unhashed_files, "file")} not hashed yet. Refresh skips hashing to stay fast; run a full scan with the acquisition tool to check for duplicates.`
                : "All files hashed."}
            </dd>
          </dl>
        </section>
      ) : null}

      {status?.documents.length ? (
        <section className="block" aria-labelledby="documents">
          <div className="block-head">
            <h2 id="documents">Documents</h2>
          </div>
          <div className="list">
            {status.documents.map((doc) => (
              <div className="list-item" key={doc.name}>
                <div>
                  <h3>
                    <code style={{ fontSize: 13.5, color: "var(--text)" }}>{doc.name}</code>
                  </h3>
                  <p className="sub">
                    {doc.present
                      ? `${formatBytes(doc.size_bytes)} · written ${formatWhen(doc.generated_at)}`
                      : "not present"}
                    {doc.error ? ` · ${doc.error}` : ""}
                  </p>
                </div>
                <div className="side">
                  <span className={`chip ${doc.error ? "err" : doc.present ? "ok" : "muted"}`}>
                    {doc.error ? "Unreadable" : doc.present ? "Present" : "Absent"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <p className="muted block" style={{ fontSize: 12.5 }}>
        System status for the rest of Continuum is on the <Link href="/status">foundation status page</Link>.
      </p>
    </>
  );
}
