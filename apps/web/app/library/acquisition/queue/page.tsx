import Link from "next/link";
import { ApiUnreachableError, type QueuePage, type SourceOut, acquisition } from "@/lib/api";
import { classLabel } from "@/lib/acquisition";
import { ChapterTally } from "../_components/ChapterTally";
import { SourceSearch } from "../_components/SourceSearch";
import { ApiDown, CoveragePill, Empty, Pill, RelationPill, Stat } from "../_components/ui";

export const dynamic = "force-dynamic";

const FILTERS = [
  { key: "", label: "Everything pending" },
  { key: "MISSING", label: "Missing" },
  { key: "PARTIAL", label: "Partial" },
  { key: "BLOCKED", label: "Blocked" },
];

/**
 * What is missing, in the order it is worth chasing.
 *
 * The queue is as long as the library is incomplete, so this screen asks the
 * API for one page and says how many there are in total. Nothing here starts
 * a download: every row ends in a search you choose to follow.
 */
export default async function QueueScreen({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; q?: string; page?: string }>;
}) {
  const params = await searchParams;
  const status = params.status ?? "";
  const query = (params.q ?? "").trim();
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);
  const limit = 25;

  let data: QueuePage | null = null;
  let sources: SourceOut[] = [];
  let error: string | null = null;
  try {
    const [queued, registry] = await Promise.all([
      acquisition.queue({ status, q: query, offset: (page - 1) * limit, limit }),
      acquisition.sources(),
    ]);
    data = queued;
    sources = registry.sources;
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / limit));
  const href = (over: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams();
    const merged = { status: status || undefined, q: query || undefined, page, ...over };
    for (const [key, value] of Object.entries(merged)) {
      if (value !== undefined && value !== "" && !(key === "page" && value === 1)) {
        next.set(key, String(value));
      }
    }
    const qs = next.toString();
    return `/library/acquisition/queue${qs ? `?${qs}` : ""}`;
  };

  return (
    <main>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Queue</h1>
      <p className="lede">
        Everything official that is missing or incomplete, main work first, then continuations,
        spin-offs, adaptations, and supplements last. Nothing here is downloaded on its own.
      </p>

      {error ? <ApiDown message={error} /> : null}

      <div className="stats">
        <Stat label="match this view" value={total} />
        <Stat label="need a decision from you" value={data?.needs_you ?? 0} tone="warn" />
        <Stat label="a source can hand over" value={data?.downloadable ?? 0} tone="ok" />
      </div>

      <form className="finder-bar" role="search" action="/library/acquisition/queue">
        <label className="sr-only" htmlFor="queue-q">
          Search the queue by work, family or alias
        </label>
        <input
          id="queue-q"
          name="q"
          type="search"
          defaultValue={query}
          placeholder="Search by work, family or alias…"
          autoComplete="off"
        />
        {status ? <input type="hidden" name="status" value={status} /> : null}
        <button className="btn small" type="submit">
          Search
        </button>
        {query ? (
          <Link className="btn small ghost" href={href({ q: undefined, page: 1 })}>
            Clear
          </Link>
        ) : null}
      </form>

      <div className="toolbar">
        <div className="chipset" role="group" aria-label="Filter the queue">
          {FILTERS.map((filter) => {
            const count = filter.key ? data?.by_status[filter.key] : undefined;
            return (
              <Link
                key={filter.key || "all"}
                className="chip"
                data-active={status === filter.key}
                href={href({ status: filter.key || undefined, page: 1 })}
              >
                {filter.label}
                {count !== undefined ? <b>{count}</b> : null}
              </Link>
            );
          })}
        </div>
      </div>

      <div className="section">
        <h2>{items.length ? `Showing ${items.length} of ${total}` : "Nothing to show"}</h2>
        <span className="hint">{pages > 1 ? `page ${page} of ${pages}` : "highest priority first"}</span>
      </div>

      {items.length ? (
        <div className="rows">
          {items.map((item) => {
            const hits = item.source_hits.filter((hit) => !("error" in hit)).length;
            return (
              <div className="row-item" key={item.work_id}>
                <div className="row-main">
                  <div className="row-title">
                    <span>{item.work}</span>
                    <RelationPill relation={item.relation} />
                    <Pill>{classLabel(item.material_class)}</Pill>
                    {item.downloadable ? <Pill tone="ok">a source can hand this over</Pill> : null}
                  </div>
                  <p className="row-meta">
                    {item.family_id ? (
                      <Link href={`/library/acquisition/families/${encodeURIComponent(item.family_id)}`}>
                        {item.family}
                      </Link>
                    ) : (
                      item.family
                    )}
                    {item.reason ? ` — ${item.reason}` : ""}
                  </p>
                  <p className="row-meta">
                    {item.best_source ? `best source: ${item.best_source}` : "no source identified yet"}
                    {item.requires_purchase ? ` · ${item.requires_purchase}` : ""}
                    {hits ? ` · ${hits} search hit${hits === 1 ? "" : "s"}` : ""}
                  </p>
                  <ChapterTally
                    held={item.chapters_held}
                    total={item.chapters_total}
                    missing={item.missing_chapters}
                  />
                  <SourceSearch
                    titles={item.search_titles}
                    sources={sources}
                    missing={item.missing_chapters}
                  />
                </div>
                <div className="row-side">
                  <CoveragePill status={item.coverage_status} />
                  {item.url ? (
                    <a className="btn small" href={item.url} target="_blank" rel="noreferrer noopener">
                      Open source
                    </a>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty title={error ? "Queue unavailable" : query || status ? "Nothing matched" : "Nothing pending"}>
          <p>
            {error
              ? "Start the API to see the queue."
              : query || status
                ? "Try a shorter search, or a different filter."
                : "Every catalogued official work is either complete or deliberately blocked."}
          </p>
        </Empty>
      )}

      {pages > 1 ? (
        <nav className="pager" aria-label="Pages">
          <Link className="btn small" href={href({ page: Math.max(1, page - 1) })} aria-disabled={page === 1}>
            ← Previous
          </Link>
          <span className="row-meta">
            {page} / {pages}
          </span>
          <Link
            className="btn small"
            href={href({ page: Math.min(pages, page + 1) })}
            aria-disabled={page === pages}
          >
            Next →
          </Link>
        </nav>
      ) : null}
    </main>
  );
}
