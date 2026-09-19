import Link from "next/link";
import { SideLink } from "./SideLink";
import "./studio.css";
import "./vault.css";
import "./catalog.css";
import "./manga.css";

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
          <Link href="/" className="wordmark" aria-label="Continuum Studio">
            CONTINUUM
          </Link>

          <nav className="side-group" aria-label="Studio">
            <SideLink href="/" exact>
              Studio
            </SideLink>
          </nav>

          <nav className="side-group" aria-label="Vault">
            <h2>Vault</h2>
            <SideLink href="/library/vault" exact also={["/library/vault/series"]}>
              Series
            </SideLink>
            <SideLink href="/library/vault/search">Search</SideLink>
            <SideLink href="/library/vault/coverage">Coverage</SideLink>
          </nav>

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

          <nav className="side-group" aria-label="Reference vault">
            <h2>Reference vault</h2>
            <SideLink href="/library/references">References</SideLink>
            <SideLink href="/library/characters">Characters</SideLink>
            <SideLink href="/library/styles">Styles &amp; modes</SideLink>
            <SideLink href="/library/datasets">Datasets &amp; tools</SideLink>
            <SideLink href="/library/inbox">Inbox</SideLink>
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
            <SideLink href="/status">System status</SideLink>
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
