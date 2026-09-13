import Link from "next/link";
import { ApiUnreachableError, type FamilyProgress, acquisition } from "@/lib/api";
import { formatBytes } from "@/lib/acquisition";
import { ApiDown, Empty, FamilyCard, Stat } from "../_components/ui";

export const dynamic = "force-dynamic";

type Sort = "attention" | "title" | "size" | "works";
type Filter = "" | "incomplete" | "review" | "empty";

const SORTS: { key: Sort; label: string }[] = [
  { key: "attention", label: "Needs attention" },
  { key: "title", label: "A–Z" },
  { key: "size", label: "Largest" },
  { key: "works", label: "Most works" },
];

const FILTERS: { key: Filter; label: string }[] = [
  { key: "", label: "All" },
  { key: "incomplete", label: "Incomplete" },
  { key: "review", label: "To review" },
  { key: "empty", label: "Nothing held yet" },
];

const PAGE = 24;

/** How far from done a family is, as a fraction: the default ordering. */
function attention(family: FamilyProgress): number {
  return (family.missing + family.partial) / Math.max(1, family.works_total);
}

function matches(family: FamilyProgress, filter: Filter): boolean {
  if (filter === "incomplete") return family.missing + family.partial > 0;
  if (filter === "review") return family.review > 0 || family.missing_folders > 0;
  if (filter === "empty") return family.files === 0;
  return true;
}

function searchHit(family: FamilyProgress, needle: string): boolean {
  if (!needle) return true;
  const hay = [family.title, ...family.aliases].join(" ").toLowerCase();
  return hay.includes(needle);
}

/**
 * Every source family, searchable.
 *
 * Filtering happens here rather than in the browser: a library is as large
 * as its owner made it, and shipping five hundred families to the client so
 * it can hide most of them is work nobody asked for. Each control is a link,
 * so the state of this screen is in the URL and the keyboard reaches all of
 * it without a line of client JavaScript.
 */
export default async function FamiliesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; sort?: string; show?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q ?? "").trim();
  const sort = (SORTS.find((s) => s.key === params.sort)?.key ?? "attention") as Sort;
  const filter = (FILTERS.find((f) => f.key === params.show)?.key ?? "") as Filter;
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let families: FamilyProgress[] = [];
  let error: string | null = null;
  try {
    families = await acquisition.families();
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const needle = query.toLowerCase();
  const shown = families.filter((f) => matches(f, filter) && searchHit(f, needle));
  shown.sort((a, b) => {
    if (sort === "title") return a.title.localeCompare(b.title);
    if (sort === "size") return b.bytes - a.bytes;
    if (sort === "works") return b.works_total - a.works_total || a.title.localeCompare(b.title);
    return attention(b) - attention(a) || a.title.localeCompare(b.title);
  });

  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const current = Math.min(page, pages);
  const slice = shown.slice((current - 1) * PAGE, current * PAGE);
  const href = (over: Record<string, string | number | undefined>) => {
    const next = new URLSearchParams();
    const merged = { q: query || undefined, sort, show: filter || undefined, page: current, ...over };
    for (const [key, value] of Object.entries(merged)) {
      if (value !== undefined && value !== "" && !(key === "page" && value === 1)) {
        next.set(key, String(value));
      }
    }
    const qs = next.toString();
    return `/library/acquisition/families${qs ? `?${qs}` : ""}`;
  };

  return (
    <main>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Families</h1>
      <p className="lede">
        A family is everything that belongs to one story: the main work, its continuations, its
        spin-offs, the adaptations and the books about it. Official is not the same as main canon,
        so each one is kept as its own kind of material.
      </p>

      {error ? <ApiDown message={error} /> : null}

      <div className="stats">
        <Stat label="families" value={families.length} />
        <Stat
          label="incomplete"
          value={families.filter((f) => f.missing + f.partial > 0).length}
          tone="warn"
        />
        <Stat
          label="waiting on review"
          value={families.filter((f) => f.review > 0).length}
          tone={families.some((f) => f.review > 0) ? "warn" : undefined}
        />
        <Stat label="on disk" value={formatBytes(families.reduce((n, f) => n + f.bytes, 0))} />
      </div>

      <form className="finder-bar" role="search" action="/library/acquisition/families">
        <label className="sr-only" htmlFor="family-q">
          Search families by title or alias
        </label>
        <input
          id="family-q"
          name="q"
          type="search"
          defaultValue={query}
          placeholder="Search by title or alias…"
          autoComplete="off"
        />
        {sort !== "attention" ? <input type="hidden" name="sort" value={sort} /> : null}
        {filter ? <input type="hidden" name="show" value={filter} /> : null}
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
        <div className="chipset" role="group" aria-label="Filter families">
          {FILTERS.map((f) => (
            <Link
              key={f.key || "all"}
              className="chip"
              data-active={filter === f.key}
              href={href({ show: f.key || undefined, page: 1 })}
            >
              {f.label}
            </Link>
          ))}
        </div>
        <div className="chipset" role="group" aria-label="Sort families">
          {SORTS.map((s) => (
            <Link
              key={s.key}
              className="chip"
              data-active={sort === s.key}
              href={href({ sort: s.key, page: 1 })}
            >
              {s.label}
            </Link>
          ))}
        </div>
      </div>

      <div className="section">
        <h2>{shown.length} shown</h2>
        <span className="hint">
          {pages > 1 ? `page ${current} of ${pages}` : "everything that matched"}
        </span>
      </div>

      {slice.length ? (
        <div className="cards">
          {slice.map((family) => (
            <FamilyCard key={family.id} family={family} />
          ))}
        </div>
      ) : (
        <Empty title={families.length ? "Nothing matched" : "No families catalogued yet"}>
          <p>
            {families.length
              ? "Try a shorter search, or clear the filter."
              : "A folder you add to the Vault becomes a family on the next scan. Nothing is invented for you."}
          </p>
          {families.length ? null : (
            <code className="cmd">python acquisition_orchestrator.py scan</code>
          )}
        </Empty>
      )}

      {pages > 1 ? (
        <nav className="pager" aria-label="Pages">
          <Link
            className="btn small"
            href={href({ page: Math.max(1, current - 1) })}
            aria-disabled={current === 1}
          >
            ← Previous
          </Link>
          <span className="row-meta">
            {current} / {pages}
          </span>
          <Link
            className="btn small"
            href={href({ page: Math.min(pages, current + 1) })}
            aria-disabled={current === pages}
          >
            Next →
          </Link>
        </nav>
      ) : null}
    </main>
  );
}
