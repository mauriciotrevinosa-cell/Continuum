/**
 * Presentational pieces shared by the Library screens.
 *
 * Server components: they render what the API projected and decide nothing.
 * None of them knows what is in anyone's library.
 */
import Link from "next/link";
import type { FamilyProgress, MaterialSummary } from "@/lib/api";
import {
  classLabel,
  formatBytes,
  plural,
  stateHint,
  stateLabel,
  stateTone,
} from "@/lib/acquisition";

export function StateChip({ state, label }: { state: string; label?: string }) {
  return (
    <span className={`chip ${stateTone(state)}`} title={stateHint(state)}>
      {label ?? stateLabel(state)}
    </span>
  );
}

export interface Segment {
  key: string;
  label: string;
  value: number;
  tone: "ok" | "warn" | "accent" | "info" | "err" | "muted";
}

/** One bar for how much of something is held, in the order of how "done" it is. */
export function CoverageBar({ segments, slim = false, label }: {
  segments: Segment[];
  slim?: boolean;
  label: string;
}) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  const described = segments.filter((s) => s.value).map((s) => `${s.value} ${s.label}`).join(", ");
  return (
    <div
      className={`coverage${slim ? " slim" : ""}`}
      role="img"
      aria-label={total ? `${label}: ${described}` : `${label}: nothing catalogued`}
    >
      {total
        ? segments
            .filter((s) => s.value)
            .map((s) => <i key={s.key} className={s.tone} style={{ width: `${(s.value / total) * 100}%` }} />)
        : null}
    </div>
  );
}

export function Legend({ segments }: { segments: Segment[] }) {
  return (
    <p className="legend">
      {segments
        .filter((s) => s.value)
        .map((s) => (
          <span key={s.key}>
            <i className={s.tone} aria-hidden />
            <b>{s.value}</b> {s.label}
          </span>
        ))}
    </p>
  );
}

export function coverageSegments(counts: {
  complete: number;
  partial: number;
  present: number;
  needs_mapping: number;
  missing: number;
  stale: number;
  unverified: number;
}): Segment[] {
  return [
    { key: "complete", label: "complete", value: counts.complete, tone: "ok" },
    { key: "present", label: "in library", value: counts.present, tone: "accent" },
    { key: "partial", label: "partial", value: counts.partial, tone: "warn" },
    { key: "mapping", label: "need mapping", value: counts.needs_mapping, tone: "info" },
    { key: "stale", label: "need a rescan", value: counts.stale, tone: "muted" },
    { key: "missing", label: "missing", value: counts.missing, tone: "err" },
    { key: "unverified", label: "unverified", value: counts.unverified, tone: "muted" },
  ];
}

/** "Manga · Complete": one kind of material in a family, as a peer of the others. */
export function MaterialLine({ material }: { material: MaterialSummary }) {
  const detail =
    material.video_files > 0
      ? plural(material.video_files, "episode file")
      : material.files
        ? formatBytes(material.bytes)
        : material.works > 1
          ? plural(material.works, "work")
          : "";
  return (
    <div className="material">
      <span className="kind">
        {classLabel(material.material_class)}
        {detail ? <small>{detail}</small> : null}
      </span>
      <StateChip state={material.state} />
    </div>
  );
}

/** A family as a collection: what it is made of, and how much of it is here. */
export function FamilyCard({ family }: { family: FamilyProgress }) {
  const story = family.materials.filter((m) => m.story);
  const supplements = family.materials.filter((m) => !m.story);
  const shown = story.length ? story.slice(0, 4) : family.materials.slice(0, 3);
  const heldShare = family.story_works || family.works_total;
  return (
    <Link className="family" href={`/library/acquisition/families/${encodeURIComponent(family.id)}`}>
      <div className="family-head">
        <h3>{family.title}</h3>
        {family.stale ? (
          <StateChip state="STALE" />
        ) : family.review_status !== "ACCEPTED" ? (
          <span className="chip info plain">New</span>
        ) : null}
      </div>
      <div className="materials">
        {shown.map((m) => (
          <MaterialLine key={m.material_class} material={m} />
        ))}
        {supplements.length && story.length ? (
          <div className="material">
            <span className="kind">
              Supplements <small>{supplements.reduce((n, m) => n + m.works, 0)} works</small>
            </span>
            <span className="muted tabular">
              {family.supplements_held}/{family.supplements} held
            </span>
          </div>
        ) : null}
      </div>
      <div>
        <CoverageBar
          slim
          label={`${family.title} story material`}
          segments={[
            { key: "held", label: "held", value: family.story_held, tone: "ok" },
            {
              key: "rest",
              label: "not held",
              value: Math.max(0, heldShare - family.story_held),
              tone: "muted",
            },
          ]}
        />
      </div>
      <div className="family-foot">
        <span>
          {plural(family.works_total, "work")} · {plural(family.materials.length, "kind")}
        </span>
        <span className="tabular">{formatBytes(family.bytes)}</span>
      </div>
    </Link>
  );
}

export function Empty({
  title,
  children,
  actions,
}: {
  title: string;
  children?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  );
}

/**
 * The API is not answering. Said calmly, with the fix one click away and the
 * technical detail folded - this is a local app, and the usual cause is that
 * its service simply is not running.
 */
export function ApiDown({ message }: { message: string }) {
  return (
    <div className="banner err" role="alert">
      <p>
        <strong>Continuum can&apos;t reach its Library service.</strong> Start it, then reload this
        page.
      </p>
      <details className="disclosure" style={{ gridColumn: "auto" }}>
        <summary>Details</summary>
        <div className="disclosure-body">
          <code>{message}</code>
        </div>
      </details>
    </div>
  );
}

export function PageHead({
  eyebrow,
  title,
  lead,
  aside,
}: {
  eyebrow: string;
  title: string;
  lead?: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="title">{title}</h1>
        {lead ? <p className="lead">{lead}</p> : null}
      </div>
      {aside ? <div>{aside}</div> : null}
    </header>
  );
}
