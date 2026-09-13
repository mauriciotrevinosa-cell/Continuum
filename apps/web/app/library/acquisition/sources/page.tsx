import { ApiUnreachableError, type SourcesView, acquisition } from "@/lib/api";
import { adapterLabel, capabilityLabel, timeAgo } from "@/lib/acquisition";
import { AddSourceForm, SourceRowActions } from "../_components/SourceControls";
import { ApiDown, Empty, PageHead } from "../_components/ui";

export const dynamic = "force-dynamic";

function host(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * The places Continuum may look. A secondary tool: calm, scannable, and
 * explicit about what each source has proved it can do.
 */
export default async function SourcesPage() {
  let data: SourcesView | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.sources();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const sources = data?.sources ?? [];
  const enabled = sources.filter((s) => s.enabled).length;

  return (
    <>
      <PageHead
        eyebrow="Acquisition"
        title="Sources"
        lead="Where Continuum may look. Each source is tested, and used only for what it proved it can do - never to get past a paywall, a login or DRM."
      />

      {error ? <ApiDown message={error} /> : null}

      {data && !data.cli_available ? (
        <div className="banner">
          <p>
            <strong>Read-only.</strong> Adding, testing and removing sources needs the acquisition
            tool to be configured. See Settings → Diagnostics.
          </p>
        </div>
      ) : null}

      {data ? (
        <>
          <section aria-labelledby="registered">
            <div className="block-head">
              <h2 id="registered">
                Registered
                <small>
                  {enabled} of {sources.length} enabled
                </small>
              </h2>
            </div>
            {sources.length ? (
              <div className="list">
                {sources.map((source) => {
                  const tone = !source.enabled
                    ? "muted"
                    : source.test_ok === false
                      ? "err"
                      : source.test_ok
                        ? "ok"
                        : "muted";
                  const status = !source.enabled
                    ? "Disabled"
                    : source.test_ok === false
                      ? "Failing"
                      : source.test_ok
                        ? "Working"
                        : "Untested";
                  return (
                    <div
                      className="list-item"
                      key={source.id}
                      style={{ opacity: source.enabled ? 1 : 0.62 }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <h3>
                          {source.name}{" "}
                          <span className="muted" style={{ fontWeight: 400, fontSize: 13 }}>
                            {source.adapter === "local-folder" ? "Local folder" : host(source.url)}
                          </span>
                        </h3>
                        <p className="sub">
                          {adapterLabel(source.adapter)}
                          {source.capabilities.length
                            ? ` · ${source.capabilities.map(capabilityLabel).join(", ")}`
                            : ""}
                        </p>
                        <p className="sub">
                          {source.test_ok === true
                            ? `Tested ${timeAgo(source.tested_at)}`
                            : source.test_ok === false
                              ? `Last test failed ${timeAgo(source.tested_at)}`
                              : "Not tested yet"}
                          {source.download_permitted ? " · downloads permitted" : ""}
                        </p>
                      </div>
                      <div className="side">
                        <span className={`chip ${tone}`}>{status}</span>
                        <SourceRowActions
                          id={source.id}
                          name={source.name}
                          enabled={source.enabled}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <Empty title="No sources yet">
                <p>Nothing is assumed for you. Add the first place Continuum may look.</p>
              </Empty>
            )}
          </section>

          <section className="block" aria-labelledby="add">
            <details className="surface" style={{ padding: "18px 24px" }} open={!sources.length}>
              <summary
                className="block-head"
                style={{ margin: 0, cursor: "pointer", listStyle: "none" }}
              >
                <h2 id="add">
                  Add a web source<small>a store, an official reader or a catalogue</small>
                </h2>
                <span className="button small">Add</span>
              </summary>
              <div style={{ marginTop: 20 }}>
                <AddSourceForm adapters={data.browser_adapters} />
              </div>
            </details>
          </section>

          <section className="block" aria-label="Folders and hosts">
            <details className="disclosure">
              <summary>Folders you own, and hosts you never use</summary>
              <div className="disclosure-body">
                <p style={{ marginTop: 0 }}>
                  A folder of files you already own can be a source too. A browser can&apos;t hand
                  one over - this app takes no filesystem paths from a page - so register it with
                  the acquisition tool and it appears in the list above.
                </p>
                <code className="cmd">
                  python acquisition_orchestrator.py sources add &lt;folder&gt; --name &quot;My
                  purchases&quot;
                </code>
                {data.unofficial_hosts.length ? (
                  <p style={{ marginBottom: 0 }}>
                    Never used as a source: {data.unofficial_hosts.join(" · ")}
                  </p>
                ) : null}
              </div>
            </details>
          </section>
        </>
      ) : null}
    </>
  );
}
