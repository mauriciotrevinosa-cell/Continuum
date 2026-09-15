import type { PageRef } from "@/lib/manga";
import { vaultImage } from "@/lib/manga";

const ROLE_TONE: Record<string, string> = { GRAMMAR: "info", TECHNIQUE: "accent", ENVIRONMENT: "ok" };

/** Full source pages in a bundle: source, role, why and what each may teach. Never identity. */
export function PageRefGrid({ refs, empty }: { refs: PageRef[]; empty: string }) {
  if (!refs.length) return <p className="hint">{empty}</p>;
  return (
    <div className="page-ref-grid">
      {refs.map((ref) => (
        <div key={`${ref.role}-${ref.locator}`} className="page-ref">
          <div className="page-ref-thumb">
            {ref.image ? (
              // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
              <img src={vaultImage(ref.image)} alt={`${ref.role} reference ${ref.label}`} loading="lazy" />
            ) : (
              <span className="muted">no preview</span>
            )}
          </div>
          <div className="stack" style={{ gap: 4 }}>
            <span className="chips">
              <span className={`chip tiny ${ROLE_TONE[ref.role] ?? "muted"}`}>{ref.role}</span>
              <span className="chip tiny quiet">{ref.status.replace("_", " ").toLowerCase()}</span>
              <span className="chip tiny quiet" title="Full pages teach page craft; they never define a character.">
                not identity
              </span>
            </span>
            <b style={{ fontSize: 12.5 }}>{ref.label}</b>
            <span className="muted" style={{ fontSize: 11.5 }}>
              {ref.series_key ?? "?"} · {ref.source}
            </span>
            <span style={{ fontSize: 12 }}>
              <span className="muted">Teaches:</span> {ref.teaches.join(", ")}
            </span>
            <ul className="why-list">
              {ref.why.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        </div>
      ))}
    </div>
  );
}
