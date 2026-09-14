/**
 * Presentational pieces for the catalog. Server-safe: no hooks.
 *
 * Identification is never presented as more certain than it is: every unit
 * shows its confidence, and anything flagged says why.
 */
import Link from "next/link";
import {
  type ContinueItem,
  type SeriesSummary,
  type UnitView,
  confidenceTone,
  kindLabel,
  progressLabel,
  unitHref,
} from "@/lib/catalog";
import { formatBytes, plural } from "@/lib/acquisition";

export function ConfidenceChip({ unit }: { unit: UnitView }) {
  if (unit.confidence === "HIGH") return null;
  return (
    <span
      className={`chip ${confidenceTone(unit.confidence)} tiny`}
      title={[...unit.evidence, ...unit.flags].join(" · ") || "No evidence recorded"}
    >
      {unit.confidence === "LOW" ? "Uncertain" : "Probable"}
    </span>
  );
}

export function SearchBox({ q = "", placeholder }: { q?: string; placeholder?: string }) {
  return (
    <form className="home-search" action="/library/vault/search" method="get" role="search">
      <label className="sr-only" htmlFor="catalog-search">
        Search the studio
      </label>
      <input
        id="catalog-search"
        name="q"
        defaultValue={q}
        placeholder={placeholder ?? "Search series, chapters, episodes, references, creators, documents…"}
        maxLength={200}
        autoComplete="off"
      />
      <button className="button primary" type="submit">
        Search
      </button>
    </form>
  );
}

function progressWidth(item: ContinueItem): number {
  const p = item.progress;
  if (p.completed_at) return 100;
  if (p.medium === "READING" && p.page_count) return Math.round(((p.page_index ?? 0) + 1) / p.page_count * 100);
  if (p.position_ms && p.duration_ms) return Math.round((p.position_ms / p.duration_ms) * 100);
  return 4;
}

export function ContinueCard({ item }: { item: ContinueItem }) {
  const target = item.state === "next" && item.next ? item.next : item.unit;
  const href = target ? unitHref(target, item.state === "next" ? null : item.progress) : null;
  const what =
    item.state === "next"
      ? item.progress.medium === "READING" ? "Next chapter" : "Next episode"
      : item.state === "finished"
        ? "Finished"
        : item.progress.medium === "READING" ? "Continue reading" : "Continue watching";
  const body = (
    <>
      <span className="what">{what}</span>
      <span className="series">{target?.series_title ?? target?.source.file_name ?? "Unavailable"}</span>
      <span className="unit">
        {target ? target.label : "This file is not in the catalog right now."}
        {item.state === "resume" ? ` · ${progressLabel(item.progress) ?? ""}` : ""}
      </span>
      <span className="progress-line" aria-hidden>
        <i style={{ width: `${progressWidth(item)}%` }} />
      </span>
    </>
  );
  return href ? (
    <Link className="continue-card" href={href}>
      {body}
    </Link>
  ) : (
    <div className="continue-card">{body}</div>
  );
}

export function SeriesCard({ series }: { series: SeriesSummary }) {
  const chapters = series.units.MANGA_CHAPTER ?? 0;
  const episodes = series.units.EPISODE ?? 0;
  const pages = series.units.ARCHIVE_PAGES ?? 0;
  const parts = [
    chapters ? plural(chapters, "chapter") : null,
    pages ? plural(pages, "page group") : null,
    episodes ? plural(episodes, "episode") : null,
  ].filter(Boolean);
  return (
    <Link className="series-card" href={`/library/vault/series/${series.series_key}`}>
      <h3>{series.title}</h3>
      <span className="counts">{parts.join(" · ") || "Other material"}</span>
      <span className="chips">
        {Object.keys(series.materials).map((m) => (
          <span key={m} className="chip quiet tiny">
            {m.toLowerCase()}
          </span>
        ))}
        {series.flagged ? <span className="chip warn tiny">{series.flagged} to check</span> : null}
        {series.last_opened_at ? <span className="chip accent tiny">In progress</span> : null}
      </span>
    </Link>
  );
}

export function UnitRow({ unit, showSeries = false }: { unit: UnitView; showSeries?: boolean }) {
  const href = unitHref(unit);
  const progress = progressLabel(unit.progress);
  const title = showSeries && unit.series_title ? `${unit.series_title} · ${unit.label}` : unit.label;
  const file = unit.source.member_name
    ? `${unit.source.member_name} — in ${unit.source.file_name}`
    : unit.source.file_name;
  return (
    <div className="unit-row">
      <div>
        <div className="name">
          {href ? <Link href={href}>{title}</Link> : <strong>{title}</strong>}
          <span className="chip quiet tiny">{kindLabel(unit.kind)}</span>
          {unit.page_count ? <span className="muted">{plural(unit.page_count, "page")}</span> : null}
          {unit.program_title && unit.kind === "EPISODE" ? (
            <span className="muted">{unit.program_title}</span>
          ) : null}
          <ConfidenceChip unit={unit} />
          {progress ? <span className="chip accent tiny">{progress}</span> : null}
        </div>
        <div className="file" title={file}>
          {file}
          {unit.source.member_bytes ? ` · ${formatBytes(unit.source.member_bytes)}` : ""}
          {unit.source.creator_handle ? ` · ${unit.source.creator_handle}` : ""}
        </div>
        {unit.flags.length ? (
          <ul className="flags">
            {unit.flags.map((flag) => (
              <li key={flag}>{flag}</li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="actions">
        {unit.open.kind === "member" ? (
          <span className="muted">{unit.source.member_cached ? "Prepared" : "In an archive"}</span>
        ) : null}
        {href ? (
          <Link className="button small" href={href}>
            {unit.kind === "EPISODE" || unit.kind === "VIDEO" ? "Watch" : unit.kind === "IMAGE" ? "View" : "Read"}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
