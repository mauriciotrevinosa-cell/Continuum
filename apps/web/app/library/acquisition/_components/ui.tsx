/**
 * Presentational pieces shared by the acquisition screens.
 *
 * Server components: they render data, they never fetch it. Every one of
 * them is content-agnostic - nothing here knows what is in anyone's library.
 */
import Link from "next/link";
import type { FamilyProgress, SourceOut, WorkRow } from "@/lib/api";
import { ChapterTally } from "./ChapterTally";
import { SourceSearch } from "./SourceSearch";
import {
  type Tone,
  classLabel,
  coverageLabel,
  coverageTone,
  formatBytes,
  relationLabel,
} from "@/lib/acquisition";

export function Pill({ tone = "muted", children }: { tone?: Tone; children: React.ReactNode }) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

export function CoveragePill({ status }: { status: string | null }) {
  return <Pill tone={coverageTone(status)}>{coverageLabel(status)}</Pill>;
}

export function RelationPill({ relation }: { relation: string | null }) {
  return <Pill tone={relation === "MAIN_WORK" ? "accent" : "muted"}>{relationLabel(relation)}</Pill>;
}

export function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string | number;
  tone?: "ok" | "warn" | "err" | "accent";
}) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

/** Complete / partial / missing / unverified, in one bar. */
export function Meter({
  complete,
  partial,
  missing,
  unknown,
}: {
  complete: number;
  partial: number;
  missing: number;
  unknown: number;
}) {
  const total = complete + partial + missing + unknown;
  if (!total) return <div className="meter" aria-hidden />;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div
      className="meter"
      role="img"
      aria-label={`${complete} complete, ${partial} partial, ${missing} missing, ${unknown} unverified`}
    >
      <i className="ok" style={{ width: pct(complete) }} />
      <i className="warn" style={{ width: pct(partial) }} />
      <i className="err" style={{ width: pct(missing) }} />
      <i className="muted" style={{ width: pct(unknown) }} />
    </div>
  );
}

export function MeterLegend() {
  return (
    <p className="meter-legend">
      <span>
        <i className="ok" />
        complete
      </span>
      <span>
        <i className="warn" />
        partial
      </span>
      <span>
        <i className="err" />
        missing
      </span>
      <span>
        <i className="muted" />
        unverified
      </span>
    </p>
  );
}

export function FamilyCard({ family }: { family: FamilyProgress }) {
  return (
    <Link className="card" href={`/library/acquisition/families/${encodeURIComponent(family.id)}`}>
      <div className="card-head">
        <h3>{family.title}</h3>
        {family.category ? <Pill>{family.category.toLowerCase()}</Pill> : null}
      </div>
      <p className="sub" style={{ fontSize: 12.5, marginBottom: 10 }}>
        {family.works_total} works · {family.files} files · {formatBytes(family.bytes)}
      </p>
      <Meter
        complete={family.complete}
        partial={family.partial}
        missing={family.missing}
        unknown={family.unknown}
      />
      <div className="pills" style={{ marginTop: 11 }}>
        {family.complete ? <Pill tone="ok">{family.complete} complete</Pill> : null}
        {family.partial ? <Pill tone="warn">{family.partial} partial</Pill> : null}
        {family.missing ? <Pill tone="err">{family.missing} missing</Pill> : null}
        {family.review ? <Pill>{family.review} to review</Pill> : null}
        {family.missing_folders ? <Pill>{family.missing_folders} folders to create</Pill> : null}
      </div>
    </Link>
  );
}

export function WorkLine({ work, sources = [] }: { work: WorkRow; sources?: SourceOut[] }) {
  const detail = [
    work.chapters && work.chapter_min !== null && work.chapter_max !== null
      ? `ch ${work.chapter_min}–${work.chapter_max} (${work.chapters})`
      : work.local_files
        ? `${work.local_files} files`
        : null,
    work.edition && work.edition !== "standard" ? work.edition : null,
    work.contained_in ? `inside ${work.contained_in}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="row-item">
      <div className="row-main">
        <div className="row-title">
          <span>{work.title}</span>
          <RelationPill relation={work.relation} />
          <Pill>{classLabel(work.material_class)}</Pill>
          {work.official === null ? <Pill tone="warn">official unverified</Pill> : null}
          {work.review_required ? <Pill tone="warn">needs review</Pill> : null}
          {work.legacy_mapping ? <Pill tone="accent">legacy path</Pill> : null}
        </div>
        <p className="row-meta">
          {detail || "nothing local yet"}
          {work.coverage_reason ? ` — ${work.coverage_reason}` : ""}
        </p>
        <ChapterTally
          held={work.chapters}
          total={work.source_chapter_count}
          latest={work.remote_latest_chapter}
          gaps={work.gaps}
          missing={work.missing_chapters}
        />
        {work.local_path ? <p className="row-meta"><code>{work.local_path}</code></p> : null}
        {work.coverage_status !== "COMPLETE" ? (
          <SourceSearch
            titles={work.search_titles}
            sources={sources}
            missing={work.missing_chapters}
          />
        ) : null}
      </div>
      <div className="row-side">
        <CoveragePill status={work.coverage_status} />
      </div>
    </div>
  );
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

export function ApiDown({ message }: { message: string }) {
  return (
    <div className="notice err">
      <strong>The Continuum API is not answering.</strong>
      <p style={{ margin: "6px 0 0", fontSize: 13 }}>{message}</p>
    </div>
  );
}

/** Where the data came from and how old it is: never leave that implicit. */
export function Provenance({
  dataDir,
  generatedAt,
  vaultRoot,
}: {
  dataDir: string;
  generatedAt: string | null;
  vaultRoot?: string;
}) {
  return (
    <p className="row-meta" style={{ marginTop: 18 }}>
      Reading <code>{dataDir || "(not configured)"}</code>
      {vaultRoot ? (
        <>
          {" "}
          · vault <code>{vaultRoot}</code>
        </>
      ) : null}
      {generatedAt ? ` · data generated ${generatedAt}` : " · no data yet"}
    </p>
  );
}
