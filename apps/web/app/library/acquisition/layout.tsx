import Link from "next/link";
import { DataBar } from "./_components/DataBar";
import { NavLink } from "./_components/NavLink";

/**
 * The application shell around every Library screen.
 *
 * Two levels, because they answer different questions. The rail says which
 * part of Continuum you are in; the strip under it says which part of the
 * Library. Collapsing them into one row would put "Sources" next to "Jobs",
 * which are not comparable choices.
 *
 * Projects and Settings are shown as what they are - not built yet. A link
 * to an empty screen would claim progress that has not happened (F-67), and
 * hiding them entirely would hide the shape of the app.
 */
export default function LibraryLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="app">
      <aside className="rail">
        <Link className="brand" href="/">
          Continuum
        </Link>
        <nav aria-label="Sections">
          <NavLink href="/library/acquisition">Library</NavLink>
          <span className="rail-soon" aria-disabled="true">
            Projects <i>later</i>
          </span>
          <Link href="/jobs">Jobs</Link>
          <span className="rail-soon" aria-disabled="true">
            Settings <i>later</i>
          </span>
        </nav>
      </aside>

      <div className="work">
        <header className="subnav" aria-label="Acquisition">
          <nav>
            <NavLink href="/library/acquisition" exact>
              Overview
            </NavLink>
            <NavLink href="/library/acquisition/families">Families</NavLink>
            <NavLink href="/library/acquisition/queue">Queue</NavLink>
            <NavLink href="/library/acquisition/sources">Sources</NavLink>
            <NavLink href="/library/acquisition/intake">Intake</NavLink>
            <NavLink href="/library/acquisition/updates">Updates</NavLink>
            <NavLink href="/library/acquisition/calendar">Calendar</NavLink>
          </nav>
          <DataBar />
        </header>
        <div className="canvas">{children}</div>
      </div>
    </div>
  );
}
