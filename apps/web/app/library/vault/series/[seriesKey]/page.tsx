import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { CatalogNotFound, type SeriesDetail, SERIES_KEY, catalog, progressLabel, unitHref } from "@/lib/catalog";
import { plural } from "@/lib/acquisition";
import { ApiDown, PageHead } from "../../../acquisition/_components/ui";
import { UnitRow } from "../../_parts";

export const dynamic = "force-dynamic";

/**
 * One series: its chapters in reading order and its episodes by season, with
 * where you left off. Videos inside archives open through the watch page,
 * which prepares them on demand.
 */
export default async function SeriesPage({ params }: { params: Promise<{ seriesKey: string }> }) {
  const { seriesKey } = await params;
  if (!SERIES_KEY.test(seriesKey)) notFound();
  let detail: SeriesDetail | null = null;
  let error: string | null = null;
  try {
    detail = await catalog.seriesDetail(seriesKey);
  } catch (cause) {
    if (cause instanceof CatalogNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!detail) {
    return <ApiDown service="catalog" message={error ?? "unavailable"} />;
  }
  const lastRead = detail.progress.reading.last_opened;
  const lastWatched = detail.progress.watching.last_opened;
  const episodes = detail.watching.reduce((n, group) => n + group.units.length, 0);

  return (
    <>
      <Link className="crumb" href="/library/vault">
        ← Series
      </Link>
      <PageHead
        eyebrow="Series"
        title={detail.title}
        lead={[
          detail.reading.length ? plural(detail.reading.length, "chapter") : null,
          episodes ? plural(episodes, "episode") : null,
          detail.uncertain ? `${detail.uncertain} uncertain identifications, marked below` : null,
          detail.duplicate_copies_hidden ? `${plural(detail.duplicate_copies_hidden, "exact copy", "exact copies")} not listed twice` : null,
        ]
          .filter(Boolean)
          .join(" · ")}
      />

      {lastRead?.unit || lastWatched?.unit ? (
        <div className="continue-row" style={{ marginBottom: 26 }}>
          {[lastRead, lastWatched].map((ref) =>
            ref?.unit ? (
              <Link key={ref.unit_key} className="continue-card" href={unitHref(ref.unit, ref.progress) ?? "#"}>
                <span className="what">{ref.progress?.medium === "READING" ? "Continue reading" : "Continue watching"}</span>
                <span className="series">{ref.unit.label}</span>
                <span className="unit">{progressLabel(ref.progress)}</span>
              </Link>
            ) : null,
          )}
        </div>
      ) : null}

      {detail.reading_groups.length ? (
        <section>
          <div className="section-title">
            <h2>Manga</h2>
          </div>
          {detail.reading_groups.map((group) => (
            <div key={group.label || "main"} className="season-block">
              {detail.reading_groups.length > 1 ? <h3>{group.label || detail.title}</h3> : null}
              <div className="unit-list">
                {group.units.map((unit) => (
                  <UnitRow key={unit.id} unit={unit} />
                ))}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {detail.watching.length ? (
        <section>
          <div className="section-title">
            <h2>Anime and video</h2>
          </div>
          {detail.watching.map((group) => (
            <div key={group.label} className="season-block">
              <h3>{group.label}</h3>
              <div className="unit-list">
                {group.units.map((unit) => (
                  <UnitRow key={unit.id} unit={unit} />
                ))}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      {detail.other.length ? (
        <section>
          <div className="section-title">
            <h2>Other material</h2>
          </div>
          <div className="unit-list">
            {detail.other.map((unit) => (
              <UnitRow key={unit.id} unit={unit} />
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
