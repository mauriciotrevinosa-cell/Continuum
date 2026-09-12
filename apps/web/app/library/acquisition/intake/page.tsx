import { ApiUnreachableError, type IntakeView, acquisition } from "@/lib/api";
import { RefreshButton } from "../_components/RefreshButton";
import { ApiDown, Empty, Pill, Stat } from "../_components/ui";
import { refreshIntakeAction } from "../actions";

export const dynamic = "force-dynamic";

function pending(action: string | undefined): boolean {
  return typeof action === "string" && action.startsWith("left-in-intake");
}

export default async function IntakePage() {
  let data: IntakeView | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.intake();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const units = data?.units ?? [];
  const waiting = units.filter((unit) => pending((unit as { action?: string }).action));

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Intake</h1>
      <p className="lede">
        The holding area between a download and the vault. Everything here is identified, hashed
        and checked against what you already have before anything is imported — and importing is a
        command you run, never something this screen does behind you.
      </p>

      {error ? <ApiDown message={error} /> : null}

      {data ? (
        <>
          <div className="stats">
            <Stat label="folders in intake" value={units.length} />
            <Stat label="unidentified" value={waiting.length} tone={waiting.length ? "warn" : undefined} />
            <Stat label="duplicate groups" value={data.duplicates.length} />
            <Stat label="conflicts" value={data.conflicts.length} tone={data.conflicts.length ? "err" : undefined} />
            <Stat label="to review" value={data.review.length} />
          </div>

          <div className="card" style={{ marginTop: 18 }}>
            <h3>Re-read the intake</h3>
            <p className="sub" style={{ fontSize: 13, margin: "4px 0 12px" }}>
              A dry run: it reports what would be imported and where. Last run:{" "}
              {data.mode ?? "never"}
              {data.intake_dirs.length ? ` · ${data.intake_dirs.join(", ")}` : ""}
            </p>
            <RefreshButton
              action={refreshIntakeAction}
              label="Re-read intake"
              busyLabel="Reading…"
              hint="nothing is copied"
            />
          </div>

          {Object.keys(data.counts).length ? (
            <>
              <div className="section">
                <h2>Last run</h2>
              </div>
              <div className="pills">
                {Object.entries(data.counts).map(([action, count]) => (
                  <Pill key={action} tone={action.startsWith("left-in-intake") ? "warn" : "ok"}>
                    {action} · {count}
                  </Pill>
                ))}
              </div>
            </>
          ) : null}

          <div className="section">
            <h2>Waiting in intake</h2>
            <span className="hint">what the importer could not place on its own</span>
          </div>
          {units.length ? (
            <div className="rows">
              {units.map((unit) => {
                const action = (unit as { action?: string }).action;
                return (
                  <div className="row-item" key={`${unit.source}/${unit.unit}`}>
                    <div className="row-main">
                      <div className="row-title">
                        <span>{unit.unit}</span>
                        <Pill>{unit.source}</Pill>
                        {unit.colored ? <Pill tone="accent">colour edition</Pill> : null}
                        {unit.unofficial_provenance.length ? (
                          <Pill tone="warn">
                            provenance: {unit.unofficial_provenance.join(", ")}
                          </Pill>
                        ) : null}
                      </div>
                      <p className="row-meta">
                        {unit.files} file{unit.files === 1 ? "" : "s"}
                        {unit.classified_by ? ` · identified by ${unit.classified_by}` : ""}
                        {unit.series.length ? ` · series: ${unit.series.join(", ")}` : ""}
                        {unit.languages.length ? ` · ${unit.languages.join(", ")}` : ""}
                      </p>
                      <p className="row-meta">
                        <code>{unit.path}</code>
                      </p>
                    </div>
                    <div className="row-side">
                      <Pill tone={pending(action) ? "warn" : "ok"}>{action ?? "pending"}</Pill>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty title="Intake is empty">
              <p>
                Drop files you have acquired into your intake folder and re-read it. They are
                identified there before anything reaches the vault.
              </p>
            </Empty>
          )}

          {data.duplicates.length ? (
            <>
              <div className="section">
                <h2>Possible duplicates</h2>
                <span className="hint">reported only — nothing is ever deleted</span>
              </div>
              <div className="rows">
                {data.duplicates.slice(0, 40).map((duplicate, index) => (
                  <div className="row-item" key={index}>
                    <div className="row-main">
                      <div className="row-title">
                        <span>{String(duplicate.family ?? "across families")}</span>
                        <Pill tone="warn">duplicate</Pill>
                      </div>
                      <p className="row-meta">{String(duplicate.detail ?? "")}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {data.proposed_moves.length ? (
            <>
              <div className="section">
                <h2>Proposed moves</h2>
                <span className="hint">never applied automatically</span>
              </div>
              <div className="rows">
                {data.proposed_moves.slice(0, 40).map((move, index) => (
                  <div className="row-item" key={index}>
                    <div className="row-main">
                      <p className="row-meta">
                        <code>{String(move.source ?? "")}</code>
                      </p>
                      <p className="row-meta">
                        → <code>{String(move.target ?? "")}</code>
                      </p>
                      <p className="row-meta">{String(move.reason ?? "")}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : null}

          {data.review.length ? (
            <>
              <div className="section">
                <h2>Needs your decision</h2>
                <span className="hint">{data.review.length} items</span>
              </div>
              <div className="rows">
                {data.review.slice(0, 60).map((item, index) => (
                  <div className="row-item" key={`${item.kind}-${index}`}>
                    <div className="row-main">
                      <div className="row-title">
                        <span>{item.item}</span>
                        <Pill tone="warn">{item.kind.replaceAll("_", " ").toLowerCase()}</Pill>
                      </div>
                      <p className="row-meta">
                        {item.family ? `${item.family} — ` : ""}
                        {item.detail}
                      </p>
                      {item.action ? <p className="row-meta">What to do: {item.action}</p> : null}
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
