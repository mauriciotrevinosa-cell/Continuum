import Link from "next/link";
import { DataBar } from "./_components/DataBar";
import { NavLink } from "./_components/NavLink";

/**
 * The Library shell.
 *
 * Library membership is not project membership: what the user owns lives
 * here, independent of any story being written. Only screens that exist are
 * linked - a placeholder for an unbuilt feature would claim progress that
 * has not happened.
 */
export default function AcquisitionLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/">
          Continuum
        </Link>
        <nav>
          <NavLink href="/library/acquisition">Overview</NavLink>
          <NavLink href="/library/acquisition/sources">Sources</NavLink>
          <NavLink href="/library/acquisition/queue">Queue</NavLink>
          <NavLink href="/library/acquisition/calendar">Calendar</NavLink>
          <NavLink href="/library/acquisition/intake">Intake</NavLink>
          <NavLink href="/library/acquisition/updates">Updates</NavLink>
        </nav>
      </header>
      <DataBar />
      {children}
    </div>
  );
}
