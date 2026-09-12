import Link from "next/link";
import { ApiUnreachableError, type QueueItem, type SourceOut, acquisition } from "@/lib/api";
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

export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  let items: QueueItem[] = [];
  let sources: SourceOut[] = [];
  let error: string | null = null;
  try {
    const [queued, registry] = await Promise.all([acquisition.queue(status), acquisition.sources()]);
    items = queued;
    sources = registry.sources;
  } catch (cause) {
    error =
      cause instanceof ApiUnreachableError ? cause.message : `Unexpected error: ${String(cause)}`;
  }

  const automatic = items.filter((item) => item.downloadable).length;

  return (
    <main style={{ padding: 0, maxWidth: "none" }}>
      <p className="eyebrow">Library · Acquisition</p>
      <h1 className="headline">Queue</h1>
      <p className="lede">
        Everything official that is missing or incomplete, in the order it is worth chasing: main
        work first, then continuations, spin-offs, adaptations, and supplements last. Nothing here
        is downloaded on its own.
      </p>

      {error ? <ApiDown message={error} /> : null}

      <div className="stats">
        <Stat label="in the queue" value={items.length} />
        <Stat label="need you" value={items.filter((i) => i.requires_user_action).length} tone="warn" />
        <Stat label="a source can hand over" value={automatic} tone="ok" />
      </div>

      <div className="btn-row" style={{ marginTop: 18 }}>
        {FILTERS.map((filter) => (
          <Link
            key={filter.key || "all"}
            className="btn small"
            href={filter.key ? `/library/acquisition/queue?status=${filter.key}` : "/library/acquisition/queue"}
            style={
              (status ?? "") === filter.key
                ? { borderColor: "var(--accent)", color: "var(--accent)" }
                : undefined
            }
          >
            {filter.label}
          </Link>
        ))}
      </div>

      <div className="section">
        <h2>{status ? `${status.toLowerCase()} works` : "Pending works"}</h2>
        <span className="hint">{items.length} shown</span>
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
        <Empty title={error ? "Queue unavailable" : "Nothing pending"}>
          <p>
            {error
              ? "Start the API to see the queue."
              : "Every catalogued official work is either complete or deliberately blocked."}
          </p>
        </Empty>
      )}
    </main>
  );
}
