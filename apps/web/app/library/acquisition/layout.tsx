import { ApiUnreachableError, type AcquisitionStatus, acquisition } from "@/lib/api";
import { plural, timeAgo } from "@/lib/acquisition";
import { AutoRefresh } from "./_components/AutoRefresh";
import { RefreshControl } from "./_components/RefreshControl";
import { SubnavLink } from "./_components/SubnavLink";

/**
 * Library Acquisition: one part of the Library, with its own navigation and
 * one honest statement of how current its data is.
 *
 * Freshness is shown on every screen because every screen is a reading of
 * documents written earlier. When the Vault has changed since then, the
 * screens say so before they say anything else.
 */
export default async function AcquisitionLayout({ children }: { children: React.ReactNode }) {
  let status: AcquisitionStatus | null = null;
  try {
    status = await acquisition.status();
  } catch (cause) {
    if (!(cause instanceof ApiUnreachableError)) throw cause;
  }
  const fresh = status?.freshness;
  const changed = fresh ? fresh.changed_families.length + fresh.changed_folders.length : 0;

  return (
    <>
      <AutoRefresh />
      <div className="section-bar">
        <div className="section-bar-row">
          <nav className="subnav" aria-label="Acquisition">
            <SubnavLink href="/library/acquisition" exact>
              Overview
            </SubnavLink>
            <SubnavLink href="/library/acquisition/families">Families</SubnavLink>
            <SubnavLink href="/library/acquisition/queue">Queue</SubnavLink>
            <SubnavLink href="/library/acquisition/sources">Sources</SubnavLink>
            <SubnavLink href="/library/acquisition/intake">Intake</SubnavLink>
            <SubnavLink href="/library/acquisition/updates">Updates</SubnavLink>
            <SubnavLink href="/library/acquisition/calendar">Calendar</SubnavLink>
          </nav>
          {status && fresh ? (
            <div className="freshness">
              <span className={`dot ${fresh.state}`} aria-hidden />
              {fresh.state === "empty" ? (
                <span>No library scan yet</span>
              ) : (
                <>
                  <span>
                    Library scanned <b>{timeAgo(fresh.library_scanned_at)}</b>
                  </span>
                  <span className="clock">
                    Catalogue <b>{timeAgo(fresh.catalogue_refreshed_at)}</b>
                  </span>
                </>
              )}
              {status.cli_available ? <RefreshControl /> : null}
            </div>
          ) : (
            <div className="freshness">
              <span className="dot unknown" aria-hidden />
              <span>Library service offline</span>
            </div>
          )}
        </div>
      </div>

      {fresh?.state === "stale" ? (
        <div className="banner" role="status">
          <p>
            <strong>Library data may be stale.</strong>{" "}
            {plural(changed, "folder")} in your Vault changed after the last scan, so anything shown
            as missing there is marked &ldquo;needs rescan&rdquo; until you refresh.
          </p>
          {status?.cli_available ? <RefreshControl variant="primary" /> : null}
        </div>
      ) : null}

      {children}
    </>
  );
}
