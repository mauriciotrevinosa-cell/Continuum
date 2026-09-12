import Link from "next/link";
import { ApiUnreachableError, type ReleaseEvent, acquisition } from "@/lib/api";
import { classLabel, relationLabel } from "@/lib/acquisition";
import { ApiDown, Empty, Pill, Stat } from "../_components/ui";

export const dynamic = "force-dynamic";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "YYYY-MM" for a month offset from another, without timezone drift. */
function shiftMonth(month: string, by: number): string {
  const [year, index] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, index - 1 + by, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function isMonth(value: string | undefined): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}$/.test(value);
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const params = await searchParams;
  let events: ReleaseEvent[] = [];
  let error: string | null = null;
  try {
    events = await acquisition.calendar();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const today = new Date();
  const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const latest = events.length ? events[events.length - 1].date.slice(0, 7) : currentMonth;
  const month = isMonth(params.month) ? params.month : currentMonth;

  const inMonth = events.filter((event) => event.date.startsWith(month));
  const byDay = new Map<string, ReleaseEvent[]>();
  for (const event of inMonth) {
    const list = byDay.get(event.date);
    if (list) list.push(event);
    else byDay.set(event.date, [event]);
  }

  const [year, monthIndex] = month.split("-").map(Number);
  const firstWeekday = (new Date(Date.UTC(year, monthIndex - 1, 1)).getUTCDay() + 6) % 7;
  const daysInMonth = new Date(Date.UTC(year, monthIndex, 0)).getUTCDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const published = events.filter((event) => event.kind === "published").length;
  const detected = events.length - published;

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Release calendar</h1>
      <p className="lede">
        When the material of your library was actually published, and when this machine noticed
        something change. Future dates stay empty on purpose: no source you have registered
        publishes a release schedule yet, and an invented date would be worse than none.
      </p>

      {error ? <ApiDown message={error} /> : null}

      <div className="stats">
        <Stat label="dated events" value={events.length} />
        <Stat label="publications" value={published} tone="accent" />
        <Stat label="changes detected" value={detected} tone="warn" />
        <Stat label="this month" value={inMonth.length} />
      </div>

      <div className="section">
        <h2>
          {MONTHS[monthIndex - 1]} {year}
        </h2>
        <span className="btn-row">
          <Link className="btn small" href={`/library/acquisition/calendar?month=${shiftMonth(month, -1)}`}>
            ← Previous
          </Link>
          <Link className="btn small" href="/library/acquisition/calendar">
            Today
          </Link>
          {latest !== month ? (
            <Link className="btn small" href={`/library/acquisition/calendar?month=${latest}`}>
              Latest activity
            </Link>
          ) : null}
          <Link className="btn small" href={`/library/acquisition/calendar?month=${shiftMonth(month, 1)}`}>
            Next →
          </Link>
        </span>
      </div>

      <div className="cal">
        {DOW.map((day) => (
          <div className="dow" key={day}>
            {day}
          </div>
        ))}
        {cells.map((day, index) => {
          if (day === null) return <div className="day blank" key={`blank-${index}`} />;
          const iso = `${month}-${String(day).padStart(2, "0")}`;
          const dayEvents = byDay.get(iso) ?? [];
          const isToday = iso === today.toISOString().slice(0, 10);
          return (
            <div
              className={`day${dayEvents.length ? " has" : ""}${isToday ? " today" : ""}`}
              key={iso}
            >
              <span className="n">{day}</span>
              {dayEvents.slice(0, 2).map((event, position) => (
                <span
                  className={`ev ${event.kind}`}
                  key={`${iso}-${position}`}
                  title={`${event.work} — ${event.detail}`}
                >
                  {event.work || event.family}
                </span>
              ))}
              {dayEvents.length > 2 ? (
                <span className="more">+{dayEvents.length - 2} more</span>
              ) : null}
            </div>
          );
        })}
      </div>

      <p className="meter-legend" style={{ marginTop: 12 }}>
        <span>
          <i style={{ background: "var(--accent)" }} />
          published
        </span>
        <span>
          <i style={{ background: "var(--warn)" }} />
          detected by Continuum
        </span>
      </p>

      <div className="section">
        <h2>What happened this month</h2>
        <span className="hint">{inMonth.length} event(s)</span>
      </div>

      {inMonth.length ? (
        <div className="rows">
          {inMonth.map((event, index) => (
            <div className="row-item" key={`${event.date}-${index}`}>
              <div className="row-main">
                <div className="row-title">
                  <span>{event.work || event.family}</span>
                  <Pill tone={event.kind === "published" ? "accent" : "warn"}>{event.kind}</Pill>
                  {event.relation ? <Pill>{relationLabel(event.relation)}</Pill> : null}
                  {event.material_class ? <Pill>{classLabel(event.material_class)}</Pill> : null}
                  {event.precision !== "day" ? (
                    <Pill>{event.precision} precision only</Pill>
                  ) : null}
                </div>
                <p className="row-meta">
                  {event.family_id ? (
                    <Link href={`/library/acquisition/families/${encodeURIComponent(event.family_id)}`}>
                      {event.family}
                    </Link>
                  ) : (
                    event.family
                  )}
                  {event.detail ? ` — ${event.detail}` : ""}
                </p>
              </div>
              <div className="row-side">
                <span className="row-meta">{event.date}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty title="Nothing dated in this month">
          <p>
            {events.length
              ? "Move to another month, or jump to the latest activity."
              : "Publication dates arrive with discovery: it reads the Japanese legal-deposit records, which carry the date each volume was registered."}
          </p>
          {!events.length ? (
            <code className="cmd">python acquisition_orchestrator.py discover</code>
          ) : null}
        </Empty>
      )}
    </main>
  );
}
