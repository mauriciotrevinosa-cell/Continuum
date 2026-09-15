import Link from "next/link";
import { AUTHORITY_LABEL, type CharacterOverview, vaultImage } from "@/lib/manga";
import { words } from "@/lib/vault";
import { ObservationCard, ReadinessGrid } from "../../../production/_parts/manga";
import { CorpusRefresh } from "./CorpusActions";

/**
 * Who this character is, what they should look like, how well grounded they
 * are, and on what evidence - before any individual reference card.
 */
export function Overview({ overview }: { overview: CharacterOverview }) {
  const { character, readiness, counts } = overview;
  const original = character.origin === "PROJECT_ORIGINAL";
  const corpusHref = `/library/characters/${character.id}/corpus`;
  return (
    <section className="block" aria-label="Character overview">
      <div className="block-head">
        <h2>Overview</h2>
      </div>
      <div className="surface panel stack">
        <div className="overview-hero">
          <div className="overview-visual">
            {overview.primary_visual ? (
              // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
              <img src={vaultImage(overview.primary_visual.image)} alt={`${character.display_name} primary production visual`} />
            ) : (
              <span>No production anchor yet - confirm observations and anchor the best ones.</span>
            )}
          </div>
          <div className="stack">
            <div className="row" style={{ gap: 8 }}>
              <span className={`chip ${original ? "accent" : "info"}`}>{original ? "Project original" : "Source work"}</span>
              {character.project_key ? <span className="chip quiet">{character.project_key}</span> : null}
              {character.source_label ? <span className="chip quiet">{character.source_label}</span> : null}
              <span className={`chip ${readiness.grounded ? "ok" : "err"}`}>
                {readiness.grounded ? "Grounded for production" : `Not grounded: ${readiness.ungrounded.join(", ")}`}
              </span>
            </div>
            {character.summary ? <p style={{ margin: 0 }}>{character.summary}</p> : null}
            <p className="hint" style={{ margin: 0 }}>
              {overview.grounding_rule}.
            </p>
            <div className="run-facts" style={{ marginTop: 0 }}>
              <span>
                <b>{counts.total}</b> observations in the corpus
              </span>
              <span>
                <b>{counts.high_authority_confirmed}</b> confirmed high-authority
              </span>
              <span>
                <b>{counts.by_status.CANDIDATE ?? 0}</b> candidates to review
              </span>
              {Object.entries(counts.by_authority).map(([authority, count]) => (
                <span key={authority}>
                  {AUTHORITY_LABEL[authority] ?? authority} <b>{count}</b>
                </span>
              ))}
            </div>
            {overview.forbidden.length ? (
              <div className="stack" style={{ gap: 2 }}>
                <span className="eyebrow" style={{ margin: 0 }}>
                  Forbidden
                </span>
                {overview.forbidden.map((f) => (
                  <span key={f} className="constraint">
                    {f}
                  </span>
                ))}
              </div>
            ) : null}
            <div className="row">
              <Link className="button small primary" href={corpusHref}>
                Explore the corpus
              </Link>
              <CorpusRefresh characterId={character.id} original={original} />
            </div>
          </div>
        </div>

        <span className="eyebrow" style={{ margin: 0 }}>
          Readiness - confirmed, high-authority, typical observations only
        </span>
        <ReadinessGrid readiness={readiness} />

        {overview.invariants.length ? (
          <div className="stack">
            <span className="eyebrow" style={{ margin: 0 }}>
              Visual invariants
            </span>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {overview.invariants.map((inv) => (
                <li key={`${inv.facet}-${inv.statement}`}>
                  <b>{words(inv.facet)}</b>: {inv.statement}{" "}
                  <span className="muted">
                    · {words(inv.state)} ({inv.supported_by} observations, {inv.distinct_sources} sources)
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <div className="stack">
          <span className="eyebrow" style={{ margin: 0 }}>
            Preferred production anchors <span className="muted">· a small curated subset - the corpus is larger</span>
          </span>
          {overview.anchors.length ? (
            <div className="obs-grid">
              {overview.anchors.map((o) => (
                <ObservationCard key={o.id} observation={o} />
              ))}
            </div>
          ) : (
            <p className="hint">No anchors yet.</p>
          )}
        </div>

        {overview.stylization.length ? (
          <div className="stack">
            <span className="eyebrow" style={{ margin: 0 }}>
              Stylization - guides rendering, never identity or body
            </span>
            <div className="obs-grid">
              {overview.stylization.map((o) => (
                <ObservationCard key={o.id} observation={o} />
              ))}
            </div>
          </div>
        ) : null}

        <div className="row" style={{ gap: 6 }}>
          {["FACE", "BODY", "WARDROBE", "EXPRESSION", "POSE", "ACCESSORY"].map((facet) => (
            <Link key={facet} className="button small ghost" href={`${corpusHref}?facet=${facet}`}>
              {words(facet)}
            </Link>
          ))}
          <Link className="button small ghost" href={`${corpusHref}?source_kind=SOURCE_PAGE`}>
            Source observations
          </Link>
          <Link className="button small ghost" href={`${corpusHref}?authority=SUPPLEMENTAL`}>
            Supplemental
          </Link>
        </div>
      </div>
    </section>
  );
}
