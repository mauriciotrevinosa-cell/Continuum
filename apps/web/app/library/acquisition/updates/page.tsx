import Link from "next/link";
import { ApiUnreachableError, type TimelineEvent, type UpdatesView, acquisition } from "@/lib/api";
import { classLabel, plural, timeAgo } from "@/lib/acquisition";
import { ApiDown, Empty, PageHead } from "../_components/ui";

export const dynamic = "force-dynamic";

function bucket(at: string | null, now: Date): string {
  if (!at) return "Undated";
  const then = new Date(at);
  const days = Math.floor((now.getTime() - then.getTime()) / 86_400_000);
  if (then.toDateString() === now.toDateString()) return "Today";
  if (days < 1 || (days === 1 && new Date(now.getTime() - 86_400_000).toDateString() === then.toDateString())) {
    return "Yesterday";
  }
  if (days < 7) return "This week";
  if (days < 31) return "This month";
  return "Earlier";
}

const KIND_TITLES: Record<TimelineEvent["kind"], string> = {
  new_chapters: "New chapters known",
  new_volumes: "New volumes known",
  new_release: "New release known",
  source_changed: "Source changed",
  local_files: "New local files",
  coverage: "Coverage changed",
  other: "Change",
};

/**
 * What changed, in order. New files on disk and new releases out in the world
 * are one feed, because both change what you should do next.
 */
export default async function UpdatesPage() {
  let data: UpdatesView | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.updates();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const now = new Date();
  const events = data?.timeline ?? [];
  const groups: { title: string; events: TimelineEvent[] }[] = [];
  for (const event of events) {
    const title = bucket(event.at, now);
    const last = groups[groups.length - 1];
    if (last && last.title === title) last.events.push(event);
    else groups.push({ title, events: [event] });
  }
  const ahead = (data?.items ?? []).filter((item) => item.update_available);

  return (
    <>
      <PageHead
        eyebrow="Library"
        title="Updates"
        lead="New files in your Vault, and new releases out in the world. Detection only: nothing is downloaded because something new appeared."
      />

      {error ? <ApiDown message={error} /> : null}

      {ahead.length ? (
        <section aria-labelledby="ahead" style={{ marginBottom: 44 }}>
          <div className="block-head">
            <h2 id="ahead">
              Ahead of your copy<small>{plural(ahead.length, "work")}</small>
            </h2>
          </div>
          <div className="list">
            {ahead.map((item) => (
              <div className="list-item" key={item.work_id || `${item.family}-${item.work}`}>
                <div>
                  <h3>{item.work}</h3>
                  <p className="sub">
                    {item.family} · you have {item.latest_local ?? "—"}, {item.latest_remote ?? "—"}{" "}
                    is known
                    {item.source ? ` · via ${item.source}` : ""}
                  </p>
                </div>
                <div className="side">
                  <span className="chip accent">New out</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {data ? (
        events.length ? (
          <section className="timeline" aria-label="Timeline">
            {groups.map((group) => (
              <div key={group.title}>
                <h3>{group.title}</h3>
                {group.events.map((event, index) => (
                  <article key={`${group.title}-${index}`} className={`event ${event.kind}`}>
                    <h4>
                      {event.family_id ? (
                        <Link href={`/library/acquisition/families/${encodeURIComponent(event.family_id)}`}>
                          {event.family}
                        </Link>
                      ) : (
                        event.family || event.work
                      )}
                      {event.material_class ? (
                        <span className="muted" style={{ fontWeight: 400 }}>
                          {" "}
                          · {classLabel(event.material_class)}
                        </span>
                      ) : null}
                    </h4>
                    <p>
                      {KIND_TITLES[event.kind]}
                      {event.detail ? ` - ${event.detail}` : ""}
                      {event.work && event.kind !== "local_files" ? ` · ${event.work}` : ""}
                    </p>
                    <time dateTime={event.at ?? undefined}>{timeAgo(event.at, now)}</time>
                  </article>
                ))}
              </div>
            ))}
          </section>
        ) : (
          <Empty title="Nothing has changed yet">
            <p>
              New files show up here after a Library refresh. New releases show up after an update
              check, which compares against a first quiet baseline.
            </p>
          </Empty>
        )
      ) : null}

      {data ? (
        <p className="muted" style={{ marginTop: 34, fontSize: 12.5 }}>
          Last release check: {timeAgo(data.last_check, now)}
        </p>
      ) : null}
    </>
  );
}
