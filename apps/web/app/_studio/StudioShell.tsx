import Link from "next/link";
import { SideLink } from "./SideLink";
import "./studio.css";

/**
 * The Continuum studio frame.
 *
 * The Library and Projects are separate parts of the application: what you
 * own, and what you make. Neither knows about any particular project; the
 * Projects group lists whatever projects exist, including none.
 */
export function StudioShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="studio">
      <div className="studio-shell">
        <aside className="sidebar">
          <Link href="/library/acquisition" className="wordmark" aria-label="Continuum Library">
            CONTINUUM
          </Link>

          <nav className="side-group" aria-label="Library">
            <h2>Library</h2>
            <SideLink href="/library/acquisition" exact>
              Overview
            </SideLink>
            <SideLink href="/library/acquisition/families">Families</SideLink>
            <SideLink
              href="/library/acquisition/queue"
              also={["/library/acquisition/sources", "/library/acquisition/calendar"]}
            >
              Acquisition
            </SideLink>
            <SideLink href="/library/acquisition/intake">Intake</SideLink>
            <SideLink href="/library/acquisition/updates">Updates</SideLink>
          </nav>

          <nav className="side-group" aria-label="Projects">
            <h2>Projects</h2>
            <SideLink href="/projects">All projects</SideLink>
          </nav>

          <nav className="side-group" aria-label="Production">
            <h2>Production</h2>
            <SideLink href="/jobs">Jobs</SideLink>
          </nav>

          <nav className="side-group" aria-label="Settings">
            <h2>Settings</h2>
            <SideLink href="/settings/diagnostics">Diagnostics</SideLink>
          </nav>

          <p className="side-foot">Local. Your Vault is read-only here.</p>
        </aside>

        <div className="stage">
          <div className="stage-inner">{children}</div>
        </div>
      </div>
    </div>
  );
}
