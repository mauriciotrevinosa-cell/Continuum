import Link from "next/link";
import { ApiUnreachableError, api, progressPercent, type JobSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

const TONE: Record<string, string> = {
  SUCCEEDED: "ok",
  RUNNING: "ok",
  FAILED_FINAL: "err",
  FAILED_RETRYABLE: "warn",
  BLOCKED: "warn",
  CANCELLED: "warn",
  CANCELLING: "warn",
  PAUSED: "warn",
  PAUSING: "warn",
};

/**
 * The production queue.
 *
 * Closing this page does not affect any job: the worker is a separate OS
 * process and the two share only PostgreSQL (ADR-0002 section 12). The page
 * is a viewer, never an owner.
 */
export default async function JobsPage() {
  let jobs: JobSummary[] = [];
  let error: string | null = null;

  try {
    jobs = await api.listJobs();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  return (
    <main>
      <div className="row">
        <h1>Jobs</h1>
        <Link href="/">← Status</Link>
      </div>
      <p className="sub">
        Work continues while this page is closed. Progress is stored in the
        database, not in the browser.
      </p>

      {error && <div className="notice err">{error}</div>}

      {!error && jobs.length === 0 && (
        <div className="panel">
          <p style={{ margin: 0 }}>No jobs yet.</p>
          <p className="sub" style={{ margin: "6px 0 0" }}>
            Enqueue a synthetic one with the command in README.md under
            &ldquo;Try the durable job system&rdquo;.
          </p>
        </div>
      )}

      {jobs.length > 0 && (
        <div className="panel">
          <table>
            <thead>
              <tr>
                <th>Type</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Attempt</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => {
                const percent = progressPercent(job);
                return (
                  <tr key={job.id}>
                    <td>
                      <Link href={`/jobs/${job.id}`}>
                        <code>{job.job_type}</code>
                      </Link>
                    </td>
                    <td>
                      <span className={`badge ${TONE[job.status] ?? ""}`}>
                        {job.status}
                      </span>
                      {job.blocked_reason && (
                        <div className="sub" style={{ margin: "4px 0 0" }}>
                          {job.blocked_reason}
                        </div>
                      )}
                    </td>
                    <td>
                      {percent === null ? (
                        "—"
                      ) : (
                        <div className="row" style={{ gap: 8 }}>
                          <div className="bar">
                            <span style={{ width: `${percent}%` }} />
                          </div>
                          <span className="sub">
                            {job.units_done}/{job.units_total}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="sub">
                      {job.attempt}/{job.max_attempts}
                    </td>
                    <td className="sub">
                      {new Date(job.created_at).toLocaleString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
