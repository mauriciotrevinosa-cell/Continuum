import Link from "next/link";
import {
  AUTHORITY_LABEL,
  AUTHORITY_ORDER,
  type Backend,
  type CorpusReadiness,
  type Observation,
  PAGE_STATE_LABEL,
  PAGE_STATE_TONE,
  type PageState,
  READINESS_TONE,
  type Reason,
  vaultImage,
} from "@/lib/manga";
import { words } from "@/lib/vault";

export function PageStateChip({ state }: { state: PageState }) {
  return <span className={`chip ${PAGE_STATE_TONE[state] ?? "muted"}`}>{PAGE_STATE_LABEL[state] ?? state}</span>;
}

/** NON-CANON SAMPLE is never mistaken for canon; canonical production says so too. */
export function PurposeBadge({ purpose }: { purpose: string }) {
  return purpose === "PRODUCTION" ? (
    <span className="sample-badge canon-badge">Canonical production</span>
  ) : (
    <span className="sample-badge" title="Never canon, never counted, never creatively approved.">
      Non-canon sample
    </span>
  );
}

export function Reasons({ reasons }: { reasons: Reason[] }) {
  if (!reasons.length) return null;
  return (
    <ul className="stack" style={{ margin: 0, paddingLeft: 18 }}>
      {reasons.map((r, index) => (
        <li key={`${r.kind}-${r.key}-${index}`}>
          <strong>{words(r.kind)}</strong>
          {r.key ? ` · ${r.key}` : ""}
          {r.detail ? ` - ${r.detail}` : ""}
          {r.old && r.new ? (
            <span className="muted mono">
              {" "}
              ({r.old.slice(0, 10)} → {r.new.slice(0, 10)})
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function ObservationCard({ observation, href }: { observation: Observation; href?: string }) {
  const body = (
    <>
      <div className="obs-thumb">
        {/* eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id */}
        <img src={vaultImage(observation.image)} alt={observation.source_label} loading="lazy" />
      </div>
      <div className="chips">
        <span className={`chip tiny ${observation.status === "CONFIRMED" ? "ok" : observation.status === "REJECTED" ? "err" : "muted"}`}>
          {words(observation.status)}
        </span>
        {observation.anchor ? <span className="chip tiny accent">Anchor</span> : null}
        {observation.atypical ? <span className="chip tiny warn">Atypical</span> : null}
        {observation.role === "STYLIZATION" ? <span className="chip tiny warn">Stylization</span> : null}
      </div>
      <span>{AUTHORITY_LABEL[observation.authority] ?? observation.authority}</span>
      <span className="muted">{observation.source_label}</span>
      {observation.facets.length || observation.angle || observation.expression ? (
        <span>
          {[...observation.facets.map(words), observation.angle ? words(observation.angle) : "", observation.expression]
            .filter(Boolean)
            .join(" · ")}
        </span>
      ) : null}
      {observation.why?.length ? <span className="why">{observation.why.join(" · ")}</span> : null}
    </>
  );
  return href ? (
    <Link className="obs-card" href={href} data-status={observation.status} data-anchor={observation.anchor}>
      {body}
    </Link>
  ) : (
    <div className="obs-card" data-status={observation.status} data-anchor={observation.anchor}>
      {body}
    </div>
  );
}

/** Observations grouped by authority, strongest first. */
export function ByAuthority({ observations, empty }: { observations: Observation[]; empty: string }) {
  if (!observations.length) return <p className="hint">{empty}</p>;
  const groups = new Map<string, Observation[]>();
  for (const o of observations) groups.set(o.authority, [...(groups.get(o.authority) ?? []), o]);
  const order = [...groups.keys()].sort((a, b) => AUTHORITY_ORDER.indexOf(a) - AUTHORITY_ORDER.indexOf(b));
  return (
    <div className="stack">
      {order.map((authority) => (
        <div key={authority} className="stack">
          <span className="eyebrow" style={{ margin: 0 }}>
            {AUTHORITY_LABEL[authority] ?? authority} <span className="muted">· {groups.get(authority)!.length}</span>
          </span>
          <div className="obs-grid">
            {groups.get(authority)!.map((o) => (
              <ObservationCard key={o.id} observation={o} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function ReadinessGrid({ readiness }: { readiness: CorpusReadiness }) {
  return (
    <div className="readiness-grid">
      {Object.entries(readiness.groups).map(([name, group]) => (
        <div key={name} className="readiness-cell">
          <span className="name">{name}</span>
          <span className={`chip ${READINESS_TONE[group.state] ?? "muted"}`}>{words(group.state)}</span>
          <span className="count">
            {group.confirmed_high_authority} confirmed high-authority · {group.distinct_sources} source
            {group.distinct_sources === 1 ? "" : "s"}
          </span>
          {group.missing_angles?.length ? (
            <span className="count muted">Missing angles: {group.missing_angles.map(words).join(", ")}</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

export function BackendList({ backends }: { backends: Backend[] }) {
  return (
    <div className="backend-list">
      {backends.map((b) => (
        <div key={b.kind} className="backend-row">
          <div className="stack" style={{ gap: 2 }}>
            <strong>{b.kind.replace("_", " ")}</strong>
            <span className="muted mono">{b.provider_id}</span>
          </div>
          <div className="stack" style={{ gap: 2 }}>
            <span>{b.reason}</span>
            {b.configured && b.kind !== "TEST" ? (
              <span className="muted">
                {b.endpoint ? `${b.endpoint} · ` : ""}
                checkpoint {b.checkpoint_available ? "available" : "not listed"} · identity conditioning{" "}
                {b.identity_conditioning ? "yes" : "no"}
                {b.model_metadata_missing?.length ? ` · model record missing: ${b.model_metadata_missing.join(", ")}` : ""}
                {b.workflow ? ` · workflow ${b.workflow.id} v${b.workflow.version}` : ""}
              </span>
            ) : null}
          </div>
          <span className="chips">
            <span className={`chip ${b.configured ? "info" : "muted"}`}>{b.configured ? "Configured" : "Not configured"}</span>
            {b.configured ? (
              <span className={`chip ${b.reachable ? "ok" : "err"}`}>{b.reachable ? "Reachable" : "Unreachable"}</span>
            ) : null}
            <span className={`chip ${b.output === "TEST_RENDER" ? "warn" : b.ready ? "ok" : "muted"}`}>
              {b.output === "TEST_RENDER" ? "Test renders only" : b.ready ? "Artwork ready" : "No artwork"}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
