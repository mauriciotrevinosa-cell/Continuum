import Link from "next/link";
import {
  ApiUnreachableError,
  type QueueGroup,
  type QueueItem,
  type QueuePage,
  type SourceOut,
  acquisition,
} from "@/lib/api";
import { classLabel, dash, plural, relationLabel } from "@/lib/acquisition";
import { SourceSearch } from "../_components/SourceSearch";
import { ApiDown, Empty, PageHead, StateChip } from "../_components/ui";

export const dynamic = "force-dynamic";

const PREVIEW = 5;
const PAGE = 25;

function QueueRow({ item, sources }: { item: QueueItem; sources: SourceOut[] }) {
  // "X of Y" only when it can be true: a release's own count can trail the
  // chapters actually held (side stories, extras), and "253 of 240" reads as
  // an error rather than a fact.
  const coverage =
    item.chapters_total && item.chapters_held && item.chapters_held <= item.chapters_total
      ? `${item.chapters_held} of ${item.chapters_total} chapters`
      : item.chapters_held
        ? `${item.chapters_held} chapters held`
        : null;
  return (
    <div className="list-item">
      <div style={{ minWidth: 0 }}>
        <h3>{item.work}</h3>
        <p className="sub">
          {item.family_id ? (
            <Link href={`/library/acquisition/families/${encodeURIComponent(item.family_id)}`}>
              {item.family}
            </Link>
          ) : (
            item.family
          )}{" "}
          · {classLabel(item.material_class)} · {relationLabel(item.relation)}
          {coverage ? ` · ${coverage}` : ""}
          {item.missing_chapters ? ` · missing ch ${dash(item.missing_chapters)}` : ""}
        </p>
        <p className="sub">
          {item.best_source ? `Best registered source: ${item.best_source}` : "No registered source for this yet"}
          {item.requires_purchase ? ` · ${item.requires_purchase}` : ""}
        </p>
        <SourceSearch titles={item.search_titles} sources={sources} missing={item.missing_chapters} />
      </div>
      <div className="side">
        <StateChip state={item.state} />
      </div>
    </div>
  );
}

/**
 * What to acquire next, grouped by why.
 *
 * A missing main series and a missing art book are both official and both
 * absent, but they are not the same errand. Official is not main canon, so
 * the reasons are kept apart and ordered by what the story needs.
 */
export default async function QueueScreen({
  searchParams,
}: {
  searchParams: Promise<{ group?: string; q?: string; page?: string }>;
}) {
  const params = await searchParams;
  const group = params.group ?? "";
  const query = (params.q ?? "").trim();
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let overview: QueuePage | null = null;
  let sources: SourceOut[] = [];
  let sections: { group: QueueGroup; page: QueuePage }[] = [];
  let focused: QueuePage | null = null;
  let error: string | null = null;

  try {
    const [first, registry] = await Promise.all([
      acquisition.queue({ limit: 1, q: query }),
      acquisition.sources(),
    ]);
    overview = first;
    sources = registry.sources;
    if (group) {
      focused = await acquisition.queue({ group, q: query, offset: (page - 1) * PAGE, limit: PAGE });
    } else {
      sections = await Promise.all(
        first.groups.map(async (g) => ({
          group: g,
          page: await acquisition.queue({ group: g.key, q: query, limit: PREVIEW }),
        })),
      );
    }
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const groups = overview?.groups ?? [];
  const active = groups.find((g) => g.key === group);
  const href = (over: Record<string, string | number | undefined>) => {
    const merged = { group: group || undefined, q: query || undefined, page, ...over };
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(merged)) {
      if (value !== undefined && value !== "" && !(key === "page" && value === 1)) qs.set(key, String(value));
    }
    const s = qs.toString();
    return `/library/acquisition/queue${s ? `?${s}` : ""}`;
  };
  const pages = focused ? Math.max(1, Math.ceil(focused.total / PAGE)) : 1;

  return (
    <>
      <PageHead
        eyebrow="Acquisition"
        title="Queue"
        lead="What to acquire next, and why. Nothing here downloads on its own: every item ends in a search you choose to open."
      />

      {error ? <ApiDown message={error} /> : null}

      {overview?.needs_mapping ? (
        <div className="banner">
          <p>
            <strong>
              {plural(overview.needs_mapping, "work")} may already be in your Library.
            </strong>{" "}
            Their local files are not matched yet, so they are left out of the queue until mapped.
          </p>
          <Link className="button small" href="/library/acquisition/intake#mapping">
            Review
          </Link>
        </div>
      ) : null}

      {groups.length ? (
        <nav className="reasons" aria-label="Reasons to acquire">
          {groups.map((g) => (
            <Link
              key={g.key}
              href={g.key === group ? href({ group: undefined, page: 1 }) : href({ group: g.key, page: 1 })}
              className={`reason ${g.tone}`}
              data-active={g.key === group}
              title={g.description}
            >
              <span className="n">{g.count}</span>
              <span className="t">{g.title}</span>
            </Link>
          ))}
        </nav>
      ) : null}

      <div className="toolbar">
        <form className="search" role="search" action="/library/acquisition/queue">
          <label className="sr-only" htmlFor="queue-q">
            Search the queue
          </label>
          <input id="queue-q" name="q" type="search" defaultValue={query} placeholder="Search by work, family or alias" autoComplete="off" />
          {group ? <input type="hidden" name="group" value={group} /> : null}
          <button className="button" type="submit">
            Search
          </button>
        </form>
        {group ? (
          <Link className="button ghost small" href={href({ group: undefined, page: 1 })}>
            All reasons
          </Link>
        ) : null}
      </div>

      {focused && active ? (
        <section aria-labelledby="focused">
          <div className="block-head">
            <h2 id="focused">
              {active.title}
              <small>{active.description}</small>
            </h2>
            <span className="muted tabular">{plural(focused.total, "work")}</span>
          </div>
          {focused.items.length ? (
            <div className="list">
              {focused.items.map((item) => (
                <QueueRow key={item.work_id} item={item} sources={sources} />
              ))}
            </div>
          ) : (
            <Empty title="Nothing matches">
              <p>Try a shorter search.</p>
            </Empty>
          )}
          {pages > 1 ? (
            <nav className="pager" aria-label="Pages">
              <Link className="button small" href={href({ page: page - 1 })} aria-disabled={page === 1}>
                Previous
              </Link>
              <span className="tabular">
                {page} / {pages}
              </span>
              <Link className="button small" href={href({ page: page + 1 })} aria-disabled={page >= pages}>
                Next
              </Link>
            </nav>
          ) : null}
        </section>
      ) : sections.length ? (
        sections.map(({ group: g, page: p }) => (
          <section key={g.key} className="block" aria-labelledby={`g-${g.key}`}>
            <div className="block-head">
              <h2 id={`g-${g.key}`}>
                {g.title}
                <small>{g.description}</small>
              </h2>
            </div>
            <div className="list">
              {p.items.map((item) => (
                <QueueRow key={item.work_id} item={item} sources={sources} />
              ))}
              {p.total > p.items.length ? (
                <div className="list-foot">
                  <Link href={href({ group: g.key, page: 1 })}>Show all {p.total} →</Link>
                </div>
              ) : null}
            </div>
          </section>
        ))
      ) : error ? null : (
        <Empty title={query ? "Nothing matches" : "Nothing to acquire"}>
          <p>
            {query
              ? "Try a shorter search."
              : "Every catalogued work is in your Library, needs mapping, or is not confirmed to exist."}
          </p>
        </Empty>
      )}
    </>
  );
}
