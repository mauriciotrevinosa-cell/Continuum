import Link from "next/link";
import { ApiUnreachableError, api, formatEta, progressPercent } from "@/lib/api";

export const dynamic = "force-dynamic";

/** Job detail: progress, blocked reason, structured error, and audit trail. */
export default async function JobDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  try {
    const job = await api.getJob(id);
    const percent = progressPercent(job);

    return (
      <main>
        <div className="row">
          <h1>
            <code>{job.job_type}</code>
          </h1>
          <Link href="/jobs">← Queue</Link>
        </div>
        <p className="sub">{job.id}</p>

        <div className="panel">
          <dl>
            <dt>Status</dt>
            <dd>
              {job.status}
              {job.blocked_reason ? ` (${job.blocked_reason})` : ""}
            </dd>
            <dt>Progress</dt>
            <dd>
              {percent === null
                ? "—"
                : `${job.units_done}/${job.units_total} (${percent}%)`}
            </dd>
            <dt>ETA</dt>
            <dd>{formatEta(job)}</dd>
            <dt>Attempt</dt>
            <dd>
              {job.attempt} of {job.max_attempts}
            </dd>
            <dt>Active time</dt>
            <dd>{(job.elapsed_active_ms / 1000).toFixed(1)}s</dd>
            <dt>Correlation id</dt>
            <dd>
              <code>{job.correlation_id ?? "—"}</code>
            </dd>
          </dl>
        </div>

        {job.remediation && (
          <>
            <h2>What to do</h2>
            <div className="notice">
              <pre>{JSON.stringify(job.remediation, null, 2)}</pre>
            </div>
          </>
        )}

        {job.last_error && (
          <>
            <h2>Last error</h2>
            <div className="notice err">
              <pre>{JSON.stringify(job.last_error, null, 2)}</pre>
            </div>
          </>
        )}

        <h2>Units</h2>
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Unit</th>
                <th>Status</th>
                <th>Attempt</th>
              </tr>
            </thead>
            <tbody>
              {job.steps.map((step) => (
                <tr key={step.unit_key}>
                  <td>
                    <code>{step.unit_key}</code>
                  </td>
                  <td>{step.status}</td>
                  <td className="sub">{step.attempt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2>Audit trail</h2>
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Event</th>
                <th>Transition</th>
              </tr>
            </thead>
            <tbody>
              {job.recent_events.map((event, index) => (
                <tr key={`${event.created_at}-${index}`}>
                  <td className="sub">
                    {new Date(event.created_at).toLocaleTimeString()}
                  </td>
                  <td>{event.event_type}</td>
                  <td className="sub">
                    {event.from_status && event.to_status
                      ? `${event.from_status} → ${event.to_status}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    );
  } catch (cause) {
    const message =
      cause instanceof ApiUnreachableError ? cause.message : String(cause);
    return (
      <main>
        <div className="row">
          <h1>Job</h1>
          <Link href="/jobs">← Queue</Link>
        </div>
        <div className="notice err">{message}</div>
      </main>
    );
  }
}
