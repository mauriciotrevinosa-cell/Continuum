import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { type SeriesSummary, catalog } from "@/lib/catalog";
import { plural } from "@/lib/acquisition";
import { ApiDown, Empty, PageHead } from "../acquisition/_components/ui";
import { SearchBox, SeriesCard } from "./_parts";

export const dynamic = "force-dynamic";

const MATERIALS = ["MANGA", "MANHWA", "ANIME", "FAN_ART", "REFERENCE", "UNKNOWN"] as const;

/** Every series the catalog found in the Vault, by material, with a filter. */
export default async function VaultSeriesPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; material?: string }>;
}) {
  const { q, material } = await searchParams;
  const chosen = MATERIALS.find((m) => m === material);
  let series: SeriesSummary[] = [];
  let error: string | null = null;
  try {
    series = await catalog.series(q, chosen);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const href = (value: string | null) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (value) params.set("material", value);
    const text = params.toString();
    return `/library/vault${text ? `?${text}` : ""}`;
  };

  return (
    <>
      <PageHead
        eyebrow="Vault"
        title="Series"
        lead="Every series folder the catalog found, with its chapters and episodes. Identification comes from folders and file names; anything uncertain is marked."
        aside={
          <Link className="button" href="/library/vault/coverage">
            Coverage
          </Link>
        }
      />
      {error ? <ApiDown service="catalog" message={error} /> : null}
      <SearchBox q={q} placeholder="Filter series by title or a known alternative title…" />
      <div className="toolbar">
        <span className="toolbar-label">Material</span>
        <nav className="segmented" aria-label="Material">
          <Link href={href(null)} data-active={!chosen}>
            All
          </Link>
          {MATERIALS.map((m) => (
            <Link key={m} href={href(m)} data-active={chosen === m}>
              {m.replace("_", " ").toLowerCase()}
            </Link>
          ))}
        </nav>
        <span className="muted">{plural(series.length, "series", "series")}</span>
      </div>
      {series.length ? (
        <div className="series-grid">
          {series.map((s) => (
            <SeriesCard key={s.series_key} series={s} />
          ))}
        </div>
      ) : error ? null : (
        <Empty title="No series match">
          <p>
            If the Vault has not been scanned yet, start a scan from{" "}
            <Link href="/library/vault/coverage">Coverage</Link>.
          </p>
        </Empty>
      )}
    </>
  );
}
