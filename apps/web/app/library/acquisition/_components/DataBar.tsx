import { ApiUnreachableError, type AcquisitionStatus, acquisition } from "@/lib/api";
import { formatWhen } from "@/lib/acquisition";
import { AutoRefresh } from "./AutoRefresh";
import { RefreshButton } from "./RefreshButton";
import { refreshDataAction } from "../actions";

/**
 * How old the data on screen is, and one control to renew it.
 *
 * Every screen renders documents the acquisition engine wrote. Without this
 * bar, a page from three days ago looks exactly like a page from a minute
 * ago - so the age is stated, always, next to the way to fix it.
 */
export async function DataBar() {
  let status: AcquisitionStatus | null = null;
  try {
    status = await acquisition.status();
  } catch (cause) {
    if (!(cause instanceof ApiUnreachableError)) throw cause;
  }

  if (!status) {
    return (
      <p className="row-meta" style={{ marginBottom: 18 }}>
        The API is not answering, so nothing on this screen is live.
      </p>
    );
  }

  const generated = status.generated_at ? new Date(status.generated_at) : null;
  const ageMinutes = generated ? (Date.now() - generated.getTime()) / 60000 : null;
  const stale = ageMinutes !== null && ageMinutes > 60;

  return (
    <div className="databar">
      <AutoRefresh seconds={60} />
      <span className="row-meta">
        {status.available ? (
          <>
            Data from <strong>{formatWhen(status.generated_at)}</strong>
            {stale ? " · older than an hour" : null}
          </>
        ) : (
          <>No acquisition data yet</>
        )}
      </span>
      <RefreshButton
        action={refreshDataAction}
        label="Re-read the Vault"
        busyLabel="Reading the Vault…"
        hint={status.cli_available ? undefined : "read-only: the CLI is not configured"}
        compact
      />
    </div>
  );
}
