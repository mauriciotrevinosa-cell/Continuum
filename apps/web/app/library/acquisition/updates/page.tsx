import { ApiUnreachableError, type UpdatesView, acquisition } from "@/lib/api";
import { formatWhen } from "@/lib/acquisition";
import { ApiDown, Empty, Pill, Stat } from "../_components/ui";

export const dynamic = "force-dynamic";

export default async function UpdatesPage() {
  let data: UpdatesView | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.updates();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const items = data?.items ?? [];
  const available = items.filter((item) => item.update_available);
  const sources = Object.entries(data?.sources ?? {});

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Update watch</h1>
      <p className="lede">
        New chapters, new volumes, newly announced side stories and new books from a publisher.
        Detection only: an alert never starts a download, because deciding to buy something is
        yours to make.
      </p>

      {error ? <ApiDown message={error} /> : null}

      {data ? (
        <>
          <div className="stats">
            <Stat label="works watched" value={items.length} />
            <Stat label="updates available" value={available.length} tone={available.length ? "warn" : "ok"} />
            <Stat label="alerts recorded" value={data.alerts.length} />
            <Stat label="sources watched" value={sources.length} />
          </div>
          <p className="row-meta" style={{ marginTop: 10 }}>
            Last remote check: {formatWhen(data.last_check)}
          </p>

          <div className="section">
            <h2>Alerts</h2>
            <span className="hint">newest first</span>
          </div>
          {data.alerts.length ? (
            <div className="rows">
              {data.alerts.slice(0, 60).map((alert, index) => (
                <div className="row-item" key={`${alert.at}-${index}`}>
                  <div className="row-main">
                    <div className="row-title">
                      <span>{alert.work ?? alert.source ?? alert.family}</span>
                      <Pill tone="accent">{alert.kind.replaceAll("_", " ").toLowerCase()}</Pill>
                    </div>
                    <p className="row-meta">
                      {alert.family ? `${alert.family} — ` : ""}
                      {alert.detail}
                    </p>
                  </div>
                  <div className="row-side">
                    <span className="row-meta">{formatWhen(alert.at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No alerts yet">
              <p>
                The first check of each work records a baseline and stays quiet. Run an update
                check to compare against it.
              </p>
              <code className="cmd">python acquisition_orchestrator.py update-check</code>
            </Empty>
          )}

          {available.length ? (
            <>
              <div className="section">
                <h2>Ahead of your copy</h2>
                <span className="hint">{available.length} works</span>
              </div>
              <div className="rows">
                {available.map((item) => (
                  <div className="row-item" key={item.work_id || `${item.family}-${item.work}`}>
                    <div className="row-main">
                      <div className="row-title">
                        <span>{item.work}</span>
                        <Pill tone="warn">
                          {item.latest_local ?? "—"} → {item.latest_remote ?? "—"}
                        </Pill>
                      </div>
                      <p className="row-meta">
                        {item.family}
                        {item.source ? ` · via ${item.source}` : ""} · checked{" "}
                        {formatWhen(item.last_checked)}
                      </p>
                    </div>
                    <div className="row-side">
                      <Pill>{item.status ?? "—"}</Pill>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {sources.length ? (
            <>
              <div className="section">
                <h2>Watched sources</h2>
                <span className="hint">a fingerprint per source, compared on each check</span>
              </div>
              <div className="rows">
                {sources.map(([id, state]) => (
                  <div className="row-item" key={id}>
                    <div className="row-main">
                      <div className="row-title">
                        <span>{id}</span>
                        {state.last_error ? <Pill tone="err">unreachable</Pill> : <Pill tone="ok">ok</Pill>}
                      </div>
                      <p className="row-meta">
                        {String(state.latest ?? state.detail ?? "")} · checked{" "}
                        {formatWhen(state.last_checked as string | null)}
                        {state.last_error ? ` · ${String(state.last_error)}` : ""}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </main>
  );
}
