import Link from "next/link";
import { ApiUnreachableError, api, type HealthResponse } from "@/lib/api";

export const dynamic = "force-dynamic";

function statusBadge(ok: boolean, label: string) {
  return <span className={`badge ${ok ? "ok" : "warn"}`}>{label}</span>;
}

/**
 * System status. The only other screen in Phase 0 is the jobs list.
 *
 * This page is also the acceptance-test surface for 110.2 (web can call the
 * API health endpoint), so it renders the real response rather than a mock.
 */
export default async function StatusPage() {
  let health: HealthResponse | null = null;
  let error: string | null = null;

  try {
    health = await api.health();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError
        ? cause.message
        : `Unexpected error: ${String(cause)}`;
  }

  return (
    <main>
      <h1>Continuum</h1>
      <p className="sub">
        Phase 0 foundation — durable jobs, safe storage, local providers. No
        library, reader or story engine yet.
      </p>

      {error && (
        <div className="notice err">
          <strong>API unreachable.</strong>
          <p style={{ margin: "6px 0 0" }}>{error}</p>
        </div>
      )}

      {health && (
        <>
          <div className="panel">
            <dl>
              <dt>Version</dt>
              <dd>
                <code>{health.version}</code>
              </dd>
              <dt>Bind address</dt>
              <dd>
                <code>{health.api_host}</code>{" "}
                {statusBadge(health.api_host === "127.0.0.1", "loopback only")}
              </dd>
              <dt>Production profile</dt>
              <dd>
                {health.production_profile}{" "}
                {statusBadge(
                  health.production_profile === "FREE_LOCAL",
                  "no paid providers",
                )}
              </dd>
            </dl>
          </div>

          <h2>Source Vault</h2>
          <div className="panel">
            <p style={{ margin: "0 0 8px" }}>
              {statusBadge(true, health.storage.vault_protection.status)}
            </p>
            <p className="sub" style={{ margin: 0 }}>
              {health.storage.vault_protection.detail}
            </p>
          </div>

          {health.storage.sync_warnings.length > 0 && (
            <>
              <h2>Warnings</h2>
              {health.storage.sync_warnings.map((warning) => (
                <div className="notice" key={warning}>
                  {warning}
                </div>
              ))}
            </>
          )}

          <h2>Storage roots</h2>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Root</th>
                  <th>Access</th>
                  <th>Present</th>
                </tr>
              </thead>
              <tbody>
                {health.storage.roots.map((root) => (
                  <tr key={root.key}>
                    <td>
                      <code>{root.key}</code>
                    </td>
                    <td>
                      {root.writable ? (
                        "read/write"
                      ) : (
                        <span className="badge ok">read-only</span>
                      )}
                    </td>
                    <td>{root.exists ? "yes" : "not attached"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2>Providers</h2>
          <div className="panel">
            <table>
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Locality</th>
                  <th>Cost</th>
                  <th>Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {health.providers.map((provider) => (
                  <tr key={provider.id}>
                    <td>
                      <code>{provider.id}</code>
                    </td>
                    <td>{provider.locality}</td>
                    <td>{provider.cost_class}</td>
                    <td className="sub" style={{ margin: 0 }}>
                      {provider.capabilities.join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h2>Jobs</h2>
      <div className="panel">
        <div className="row">
          <span>Durable background work, independent of this page.</span>
          <Link href="/jobs">Open queue →</Link>
        </div>
      </div>
    </main>
  );
}
