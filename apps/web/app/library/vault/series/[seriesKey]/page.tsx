import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { CatalogNotFound, type SeriesDetail, SERIES_KEY, type UnitView, catalog, progressLabel, unitHref } from "@/lib/catalog";
import { plural } from "@/lib/acquisition";
import { ApiDown, PageHead } from "../../../acquisition/_components/ui";
import { UnitRow } from "../../_parts";

export const dynamic = "force-dynamic";

/** Units per collapsible range. Long series stay navigable; every unit stays one click away. */
const RANGE = 50;

function rangeLabel(units: UnitView[], noun: string): string {
  const number = (u: UnitView) => u.chapter_number ?? (u.episode !== null ? String(u.episode) : null);
  const numbered = units.map(number).filter((n): n is string => Boolean(n));
  const unnumbered = units.length - numbered.length;
  const extra = unnumbered ? ` + ${unnumbered} unnumbered` : "";
  if (numbered.length) {
    const [a, b] = [numbered[0], numbered[numbered.length - 1]];
    return (a === b ? `${noun} ${a}` : `${noun}s ${a}–${b}`) + extra;
  }
  return `${units[0].label} – ${units[units.length - 1].label}`;
}

function chunks(units: UnitView[]): UnitView[][] {
  const out: UnitView[][] = [];
  for (let i = 0; i < units.length; i += RANGE) out.push(units.slice(i, i + RANGE));
  return out;
}

/** A group of units: short groups list directly; long ones fold into ranges. */
function UnitGroup({ units, noun, focus }: { units: UnitView[]; noun: string; focus: string | null }) {
  if (units.length <= RANGE) {
    return (
      <div className="unit-list">
        {units.map((unit) => (
          <UnitRow key={unit.id} unit={unit} />
        ))}
      </div>
    );
  }
  const parts = chunks(units);
  const focused = parts.findIndex((part) => part.some((u) => u.unit_key === focus));
  return (
    <div className="unit-ranges">
      {parts.map((part, index) => {
        const opened = part.filter((u) => u.progress).length;
        return (
          <details key={part[0].id} className="unit-range" open={index === focused}>
            <summary>
              <span>{rangeLabel(part, noun)}</span>
              <span className="muted">
                {plural(part.length, noun.toLowerCase())}
                {opened ? ` · ${opened} opened` : ""}
                {index === focused ? " · where you left off" : ""}
              </span>
            </summary>
            <div className="unit-list">
              {part.map((unit) => (
                <UnitRow key={unit.id} unit={unit} />
              ))}
            </div>
          </details>
        );
      })}
    </div>
  );
}

/**
 * One series: its chapters in reading order and its episodes by season, with
 * where you left off. Long lists fold into collapsible sections and ranges so
 * the overview stays compact; every chapter and episode is still one click
 * away. Videos inside archives open through the watch page, which prepares
 * them on demand.
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
  const chapters = detail.reading_groups.reduce((n, group) => n + group.units.length, 0);
  const episodes = detail.watching.reduce((n, group) => n + group.units.length, 0);
  const compact = chapters + episodes > RANGE;
  const readFocus = lastRead?.unit_key ?? null;
  const watchFocus = lastWatched?.unit_key ?? null;

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
                <span className="unit">{progressLabel(ref.progress, ref.unit.first_page_index ?? 0)}</span>
              </Link>
            ) : null,
          )}
        </div>
      ) : null}

      {detail.reading_groups.length ? (
        <details className="series-section" open>
          <summary>
            <h2>Manga</h2>
            <span className="muted">
              {plural(chapters, "chapter")}
              {detail.reading_groups.length > 1 ? ` · ${plural(detail.reading_groups.length, "work")}` : ""}
            </span>
          </summary>
          {detail.reading_groups.map((group) =>
            detail.reading_groups.length > 1 ? (
              <details
                key={group.label || "main"}
                className="season-block"
                open={group.units.some((u) => u.unit_key === readFocus) || group.units.length <= 12}
              >
                <summary>
                  <h3>{group.label || detail.title}</h3>
                  <span className="muted">{plural(group.units.length, "chapter")}</span>
                </summary>
                <UnitGroup units={group.units} noun="Chapter" focus={readFocus} />
              </details>
            ) : (
              <div key={group.label || "main"} className="season-block">
                <UnitGroup units={group.units} noun="Chapter" focus={readFocus} />
              </div>
            ),
          )}
        </details>
      ) : null}

      {detail.watching.length ? (
        <details className="series-section" open>
          <summary>
            <h2>Anime and video</h2>
            <span className="muted">
              {plural(episodes, "episode")} · {plural(detail.watching.length, "group")}
            </span>
          </summary>
          {detail.watching.map((group) => (
            <details
              key={group.label}
              className="season-block"
              open={
                detail!.watching.length === 1 ||
                group.units.some((u) => u.unit_key === watchFocus) ||
                (!watchFocus && group === detail!.watching[0] && !compact)
              }
            >
              <summary>
                <h3>{group.label}</h3>
                <span className="muted">{plural(group.units.length, "episode")}</span>
              </summary>
              <UnitGroup units={group.units} noun="Episode" focus={watchFocus} />
            </details>
          ))}
        </details>
      ) : null}

      {detail.other.length ? (
        <details className="series-section" open={detail.other.length <= 12}>
          <summary>
            <h2>Other material</h2>
            <span className="muted">{plural(detail.other.length, "item")}</span>
          </summary>
          <UnitGroup units={detail.other} noun="Item" focus={null} />
        </details>
      ) : null}
    </>
  );
}
