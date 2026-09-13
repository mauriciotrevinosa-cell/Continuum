import Link from "next/link";
import { ApiUnreachableError, type FamilyProgress, acquisition } from "@/lib/api";
import { classLabel } from "@/lib/acquisition";
import { ApiDown, Empty, FamilyCard, PageHead } from "../_components/ui";

export const dynamic = "force-dynamic";

const STATES = [
  { key: "", label: "All" },
  { key: "complete", label: "Complete" },
  { key: "partial", label: "Partial" },
  { key: "missing", label: "Missing" },
  { key: "review", label: "Needs review" },
] as const;

const SORTS = [
  { key: "attention", label: "Needs attention" },
  { key: "name", label: "Name" },
  { key: "completion", label: "Completion" },
  { key: "recent", label: "Recently changed" },
  { key: "storage", label: "Storage" },
] as const;

type StateKey = (typeof STATES)[number]["key"];
type SortKey = (typeof SORTS)[number]["key"];

const PAGE = 24;

function share(f: FamilyProgress): number {
  const base = f.story_works || f.works_total;
  return base ? f.story_held / base : 0;
}

function inState(f: FamilyProgress, state: StateKey): boolean {
  switch (state) {
    case "complete":
      return f.state === "COMPLETE" || f.state === "PRESENT";
    case "partial":
      return f.state === "PARTIAL";
    case "missing":
      return f.state === "MISSING";
    case "review":
      return (
        f.state === "NEEDS_MAPPING" ||
        f.state === "UNCATALOGUED" ||
        f.stale ||
        f.review > 0 ||
        f.review_status !== "ACCEPTED"
      );
    default:
      return true;
  }
}

/**
 * Every family, findable. Filtering and sorting happen on the server from the
 * URL, so the state of the screen can be bookmarked and the keyboard reaches
 * every control without client code.
 */
export default async function FamiliesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; state?: string; material?: string; sort?: string; page?: string }>;
}) {
  const params = await searchParams;
  const query = (params.q ?? "").trim();
  const state = (STATES.find((s) => s.key === params.state)?.key ?? "") as StateKey;
  const sort = (SORTS.find((s) => s.key === params.sort)?.key ?? "attention") as SortKey;
  const material = params.material ?? "";
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let families: FamilyProgress[] = [];
  let error: string | null = null;
  try {
    families = await acquisition.families();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const materials = [...new Set(families.flatMap((f) => f.materials.filter((m) => m.story).map((m) => m.material_class)))].sort();
  const needle = query.toLowerCase();
  const shown = families.filter(
    (f) =>
      inState(f, state) &&
      (!material || f.materials.some((m) => m.material_class === material && (m.files > 0 || m.works > 0))) &&
      (!needle || [f.title, ...f.aliases].some((name) => name.toLowerCase().includes(needle))),
  );
  shown.sort((a, b) => {
    switch (sort) {
      case "name":
        return a.title.localeCompare(b.title);
      case "completion":
        return share(b) - share(a) || a.title.localeCompare(b.title);
      case "recent":
        return (b.last_added_at ?? "").localeCompare(a.last_added_at ?? "");
      case "storage":
        return b.bytes - a.bytes;
      default:
        return b.attention - a.attention || a.title.localeCompare(b.title);
    }
  });

  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  const current = Math.min(page, pages);
  const href = (over: Record<string, string | number | undefined>) => {
    const merged: Record<string, string | number | undefined> = {
      q: query || undefined,
      state: state || undefined,
      material: material || undefined,
      sort: sort === "attention" ? undefined : sort,
      page: current,
      ...over,
    };
    const qs = new URLSearchParams();
    for (const [key, value] of Object.entries(merged)) {
      if (value !== undefined && value !== "" && !(key === "page" && value === 1)) qs.set(key, String(value));
    }
    const s = qs.toString();
    return `/library/acquisition/families${s ? `?${s}` : ""}`;
  };

  return (
    <>
      <PageHead
        eyebrow="Library"
        title="Families"
        lead="Everything that belongs to one story: the series, its continuations and spin-offs, its adaptations, and the books about it."
      />

      {error ? <ApiDown message={error} /> : null}

      <div className="toolbar">
        <form className="search" role="search" action="/library/acquisition/families">
          <label className="sr-only" htmlFor="family-q">
            Search families by title or alias
          </label>
          <input id="family-q" name="q" type="search" defaultValue={query} placeholder="Search by title or alias" autoComplete="off" />
          {state ? <input type="hidden" name="state" value={state} /> : null}
          {material ? <input type="hidden" name="material" value={material} /> : null}
          {sort !== "attention" ? <input type="hidden" name="sort" value={sort} /> : null}
          <button className="button" type="submit">
            Search
          </button>
        </form>
      </div>

      <div className="toolbar">
        <nav className="segmented" aria-label="Filter by state">
          {STATES.map((s) => (
            <Link key={s.key || "all"} href={href({ state: s.key || undefined, page: 1 })} data-active={state === s.key}>
              {s.label}
              <b>{families.filter((f) => inState(f, s.key)).length}</b>
            </Link>
          ))}
        </nav>
        {materials.length > 1 ? (
          <nav className="segmented" aria-label="Filter by material">
            <Link href={href({ material: undefined, page: 1 })} data-active={!material}>
              Any material
            </Link>
            {materials.map((m) => (
              <Link key={m} href={href({ material: m, page: 1 })} data-active={material === m}>
                {classLabel(m)}
              </Link>
            ))}
          </nav>
        ) : null}
        <span className="toolbar-label">Sort</span>
        <nav className="segmented" aria-label="Sort families">
          {SORTS.map((s) => (
            <Link key={s.key} href={href({ sort: s.key, page: 1 })} data-active={sort === s.key}>
              {s.label}
            </Link>
          ))}
        </nav>
      </div>

      {shown.length ? (
        <>
          <p className="muted" style={{ margin: "0 0 14px" }}>
            {shown.length === families.length
              ? `${families.length} families`
              : `${shown.length} of ${families.length} families`}
            {pages > 1 ? ` · page ${current} of ${pages}` : ""}
          </p>
          <div className="collection">
            {shown.slice((current - 1) * PAGE, current * PAGE).map((family) => (
              <FamilyCard key={family.id} family={family} />
            ))}
          </div>
        </>
      ) : error ? null : (
        <Empty
          title={families.length ? "No family matches" : "No families yet"}
          actions={
            families.length ? (
              <Link className="button" href="/library/acquisition/families">
                Clear filters
              </Link>
            ) : null
          }
        >
          <p>
            {families.length
              ? "Try a shorter search or another filter."
              : "A folder in your Vault becomes a family the next time the Library is scanned."}
          </p>
        </Empty>
      )}

      {pages > 1 ? (
        <nav className="pager" aria-label="Pages">
          <Link className="button small" href={href({ page: current - 1 })} aria-disabled={current === 1}>
            Previous
          </Link>
          <span className="tabular">
            {current} / {pages}
          </span>
          <Link className="button small" href={href({ page: current + 1 })} aria-disabled={current === pages}>
            Next
          </Link>
        </nav>
      ) : null}
    </>
  );
}
