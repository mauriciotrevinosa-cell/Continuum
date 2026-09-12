import { ApiUnreachableError, type SourcesView, acquisition } from "@/lib/api";
import { adapterLabel, capabilityLabel, formatWhen } from "@/lib/acquisition";
import { AddSourceForm, SourceRowActions } from "../_components/SourceControls";
import { ApiDown, Empty, Pill, Stat } from "../_components/ui";

export const dynamic = "force-dynamic";

const CAPABILITY_TONE: Record<string, "ok" | "accent" | "warn" | "muted"> = {
  AUTOMATIC_ACQUISITION: "ok",
  MANUAL_ACQUISITION: "accent",
  UPDATE_TRACKING: "muted",
  METADATA: "muted",
  DISCOVERY_ONLY: "muted",
};

export default async function SourcesPage() {
  let data: SourcesView | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.sources();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Sources</h1>
      <p className="lede">
        The places Continuum may look. You add them; each one is probed to find out what it can
        actually do, and it is used only for what it proved it can do. A source is never used to
        bypass DRM, a paywall, a login or a robots rule.
      </p>

      {error ? <ApiDown message={error} /> : null}

      {data ? (
        <>
          <div className="stats">
            <Stat label="registered" value={data.sources.length} />
            <Stat label="enabled" value={data.sources.filter((s) => s.enabled).length} tone="ok" />
            <Stat
              label="can acquire"
              value={data.sources.filter((s) => s.capabilities.includes("AUTOMATIC_ACQUISITION")).length}
              tone="accent"
            />
            <Stat
              label="untested"
              value={data.sources.filter((s) => s.test_ok === null).length}
              tone="warn"
            />
            <Stat label="never used" value={data.unofficial_hosts.length} />
          </div>

          {!data.cli_available ? (
            <div className="notice" style={{ marginTop: 18 }}>
              <strong>Read-only.</strong>
              <p style={{ margin: "6px 0 0", fontSize: 13 }}>
                The acquisition CLI is not configured, so adding, testing and removing sources will
                answer with the command to run instead of doing it. Set{" "}
                <code>CONTINUUM_ACQUISITION_CLI</code> to the full path of{" "}
                <code>acquisition_orchestrator.py</code> to enable them here.
              </p>
            </div>
          ) : null}

          <div className="section">
            <h2>Add a source</h2>
            <span className="hint">a website, a catalogue, or a folder you own</span>
          </div>
          <div className="card">
            <AddSourceForm adapters={data.adapters} />
          </div>

          <div className="section">
            <h2>Registered</h2>
            <span className="hint">{data.sources.length} in the registry</span>
          </div>
          {data.sources.length ? (
            <div className="rows">
              {data.sources.map((source) => (
                <div className="row-item" key={source.id} style={{ opacity: source.enabled ? 1 : 0.62 }}>
                  <div className="row-main">
                    <div className="row-title">
                      <span>{source.name}</span>
                      <Pill>{adapterLabel(source.adapter)}</Pill>
                      {source.enabled ? null : <Pill tone="warn">disabled</Pill>}
                      {source.test_ok === true ? <Pill tone="ok">tested</Pill> : null}
                      {source.test_ok === false ? <Pill tone="err">failing</Pill> : null}
                      {source.test_ok === null ? <Pill>untested</Pill> : null}
                      {source.download_permitted ? <Pill tone="ok">download permitted</Pill> : null}
                    </div>
                    <p className="row-meta">
                      <code>{source.url}</code>
                    </p>
                    <div className="pills" style={{ marginTop: 6 }}>
                      {source.capabilities.map((capability) => (
                        <Pill key={capability} tone={CAPABILITY_TONE[capability] ?? "muted"}>
                          {capabilityLabel(capability)}
                        </Pill>
                      ))}
                      {source.roles.map((role) => (
                        <Pill key={role}>{role}</Pill>
                      ))}
                    </div>
                    <p className="row-meta">
                      {source.operations.length
                        ? `operations: ${source.operations.join(", ")}`
                        : "operations: not probed yet"}
                      {" · "}
                      tested {formatWhen(source.tested_at)}
                      {source.test_error ? ` · ${source.test_error}` : ""}
                    </p>
                    {source.notes ? <p className="row-meta">{source.notes}</p> : null}
                  </div>
                  <div className="row-side">
                    <SourceRowActions id={source.id} enabled={source.enabled} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No sources registered">
              <p>
                Add the first one above. Nothing is assumed for you: an empty registry is a valid
                state, and Continuum simply has nowhere to look until you say where.
              </p>
            </Empty>
          )}

          <div className="section">
            <h2>Never used as a source</h2>
            <span className="hint">refused when adding, and ignored everywhere else</span>
          </div>
          {data.unofficial_hosts.length ? (
            <div className="pills">
              {data.unofficial_hosts.map((host) => (
                <Pill key={host} tone="err">
                  {host}
                </Pill>
              ))}
            </div>
          ) : (
            <p className="row-meta">
              None listed. Add one with{" "}
              <code>acquisition_orchestrator.py sources unofficial &lt;host&gt;</code>.
            </p>
          )}
        </>
      ) : null}
    </main>
  );
}
