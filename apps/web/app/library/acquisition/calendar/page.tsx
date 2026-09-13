import Link from "next/link";
import { ApiUnreachableError, type ReleaseEvent, acquisition } from "@/lib/api";
import { classLabel, relationLabel } from "@/lib/acquisition";
import { ApiDown, Empty, PageHead } from "../_components/ui";

export const dynamic = "force-dynamic";

const GROUPS = ["Today", "This week", "Later", "Recently", "Earlier"] as const;
type Group = (typeof GROUPS)[number];

const RECENT_DAYS = 90;
const EARLIER_LIMIT = 60;

function dayStart(date: Date): number {
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
}

function groupOf(event: ReleaseEvent, today: number): Group {
  const [y, m, d] = event.date.split("-").map(Number);
  const at = Date.UTC(y, m - 1, d);
  const days = Math.round((at - today) / 86_400_000);
  if (event.precision === "day" && days === 0) return "Today";
  if (event.precision === "day" && days > 0 && days <= 7) return "This week";
  if (days > 0) return "Later";
  if (days >= -RECENT_DAYS) return "Recently";
  return "Earlier";
}

function displayDate(event: ReleaseEvent): { main: string; note?: string } {
  const [y, m, d] = event.date.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  if (event.precision === "year") return { main: String(y), note: "year only" };
  if (event.precision === "month") {
    return { main: date.toLocaleDateString(undefined, { month: "short", year: "numeric", timeZone: "UTC" }), note: "month only" };
  }
  return { main: date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) };
}

/**
 * Release dates, grouped the way people plan: today, this week, later. Dates
 * are shown with the precision they were recorded at - a record that gives
 * only a year is never displayed as if it named a day.
 */
export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ material?: string; family?: string }>;
}) {
  const params = await searchParams;
  let events: ReleaseEvent[] = [];
  let error: string | null = null;
  try {
    events = await acquisition.calendar();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const material = params.material ?? "";
  const family = params.family ?? "";
  const materials = [...new Set(events.map((e) => e.material_class).filter(Boolean) as string[])].sort();
  const families = [...new Map(events.filter((e) => e.family_id).map((e) => [e.family_id, e.family])).entries()].sort(
    (a, b) => a[1].localeCompare(b[1]),
  );
  const shown = events.filter(
    (e) => (!material || e.material_class === material) && (!family || e.family_id === family),
  );
  const today = dayStart(new Date());
  const grouped = new Map<Group, ReleaseEvent[]>();
  for (const event of shown) {
    const g = groupOf(event, today);
    grouped.set(g, [...(grouped.get(g) ?? []), event]);
  }
  for (const [g, list] of grouped) {
    list.sort((a, b) => (g === "Later" || g === "This week" ? a.date.localeCompare(b.date) : b.date.localeCompare(a.date)));
  }

  return (
    <>
      <PageHead
        eyebrow="Acquisition"
        title="Calendar"
        lead="When the material in your Library was published, and what is coming. No registered source publishes a schedule yet, so future dates appear only when a record states one."
      />

      {error ? <ApiDown message={error} /> : null}

      {events.length ? (
        <form className="toolbar" action="/library/acquisition/calendar">
          <label className="sr-only" htmlFor="cal-material">
            Material
          </label>
          <select id="cal-material" name="material" defaultValue={material} className="button">
            <option value="">All material</option>
            {materials.map((m) => (
              <option key={m} value={m}>
                {classLabel(m)}
              </option>
            ))}
          </select>
          <label className="sr-only" htmlFor="cal-family">
            Family
          </label>
          <select id="cal-family" name="family" defaultValue={family} className="button" style={{ maxWidth: 360 }}>
            <option value="">All families</option>
            {families.map(([id, title]) => (
              <option key={id} value={id}>
                {title}
              </option>
            ))}
          </select>
          <button className="button" type="submit">
            Show
          </button>
          {material || family ? (
            <Link className="button ghost small" href="/library/acquisition/calendar">
              Clear
            </Link>
          ) : null}
        </form>
      ) : null}

      {shown.length ? (
        GROUPS.filter((g) => grouped.get(g)?.length).map((g) => {
          const list = grouped.get(g) ?? [];
          const visible = g === "Earlier" ? list.slice(0, EARLIER_LIMIT) : list;
          const body = (
            <div className="list dates">
              {visible.map((event, index) => {
                const when = displayDate(event);
                return (
                  <div className="list-item" key={`${event.date}-${event.work_id}-${index}`}>
                    <div className="date">
                      {when.main}
                      {when.note ? <small>{when.note}</small> : null}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <h3>{event.work || event.family}</h3>
                      <p className="sub">
                        {event.family_id ? (
                          <Link href={`/library/acquisition/families/${encodeURIComponent(event.family_id)}`}>
                            {event.family}
                          </Link>
                        ) : (
                          event.family
                        )}
                        {event.material_class ? ` · ${classLabel(event.material_class)}` : ""}
                        {event.relation ? ` · ${relationLabel(event.relation)}` : ""}
                        {event.detail ? ` · ${event.detail}` : ""}
                      </p>
                    </div>
                    <div className="side">
                      <span className={`chip ${event.kind === "published" ? "quiet" : "accent"}`}>
                        {event.kind === "published" ? "Published" : "Detected"}
                      </span>
                    </div>
                  </div>
                );
              })}
              {g === "Earlier" && list.length > visible.length ? (
                <div className="list-foot muted">
                  {list.length - visible.length} earlier dates not shown. Filter by family to see
                  them.
                </div>
              ) : null}
            </div>
          );
          return (
            <section key={g} className="block" aria-labelledby={`g-${g.replaceAll(" ", "-")}`}>
              {g === "Earlier" ? (
                <details className="supplements">
                  <summary className="block-head">
                    <h2 id={`g-${g.replaceAll(" ", "-")}`}>
                      Earlier<small>{list.length} dates</small>
                    </h2>
                    <span className="toggle" />
                  </summary>
                  {body}
                </details>
              ) : (
                <>
                  <div className="block-head">
                    <h2 id={`g-${g.replaceAll(" ", "-")}`}>
                      {g}
                      <small>{list.length}</small>
                    </h2>
                  </div>
                  {body}
                </>
              )}
            </section>
          );
        })
      ) : error ? null : (
        <Empty title={events.length ? "No dates match" : "No dates known yet"}>
          <p>
            {events.length
              ? "Try another material or family."
              : "Publication dates arrive with a catalogue refresh, from the records that list when each volume was published."}
          </p>
        </Empty>
      )}
    </>
  );
}
