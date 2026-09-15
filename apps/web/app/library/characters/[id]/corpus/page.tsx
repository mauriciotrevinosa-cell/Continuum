import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import {
  ANGLES,
  AUTHORITY_LABEL,
  AUTHORITY_ORDER,
  type CharacterOverview,
  FACETS,
  type ObservationList,
  manga,
} from "@/lib/manga";
import { VaultNotFound, words } from "@/lib/vault";
import { ApiDown } from "../../../acquisition/_components/ui";
import { ObservationCard } from "../../../../production/_parts/manga";
import { ObservationReview } from "../CorpusActions";

export const dynamic = "force-dynamic";

const STATUSES = ["CANDIDATE", "CONFIRMED", "REJECTED"];
const SOURCES = ["CURATED", "SOURCE_PAGE", "FAN_ART", "APPROVED_OUTPUT"];

/**
 * The character reference corpus: every observation, filterable by what it
 * teaches and how authoritative it is, or ranked for a need (facet, angle,
 * expression, another character). Candidates are confirmed here.
 */
export default async function CorpusPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  if (!/^[0-9a-f-]{36}$/.test(id)) notFound();
  const filters = {
    status: query.status,
    authority: query.authority,
    source_kind: query.source_kind,
    facet: query.facet,
    angle: query.angle,
    expression: query.expression,
    with_character: query.with_character,
    ranked: query.ranked,
    limit: query.limit ?? "60",
    offset: query.offset,
  };
  let overview: CharacterOverview | null = null;
  let list: ObservationList | null = null;
  let error: string | null = null;
  try {
    [overview, list] = await Promise.all([manga.overview(id), manga.observations(id, filters)]);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!overview || !list) return <ApiDown service="character corpus" message={error ?? "no response"} />;
  const offset = Number(query.offset ?? 0);
  const limit = Number(filters.limit);
  const pageHref = (next: number) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries({ ...filters, offset: String(next) })) if (value) search.set(key, value);
    return `?${search.toString()}`;
  };

  return (
    <>
      <Link className="crumb" href={`/library/characters/${id}`}>
        ← {overview.character.display_name}
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">Character reference corpus</p>
          <h1 className="title">{overview.character.display_name}</h1>
          <p className="lead">
            {overview.counts.total} observations · {overview.counts.high_authority_confirmed} confirmed high-authority ·{" "}
            {overview.counts.by_status.CANDIDATE ?? 0} candidates. Production retrieves a few relevant observations per
            page; the corpus holds the evidence.
          </p>
        </div>
      </header>

      <form className="surface panel form-row" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", alignItems: "end" }}>
        {[
          ["status", STATUSES],
          ["authority", AUTHORITY_ORDER],
          ["source_kind", SOURCES],
          ["facet", [...FACETS]],
          ["angle", [...ANGLES]],
        ].map(([name, options]) => (
          <div className="field compact" key={name as string}>
            <label>
              {words(name as string)}
              <select name={name as string} defaultValue={query[name as string] ?? ""}>
                <option value="">Any</option>
                {(options as string[]).map((o) => (
                  <option key={o} value={o}>
                    {name === "authority" ? (AUTHORITY_LABEL[o] ?? o) : words(o)}
                  </option>
                ))}
              </select>
            </label>
          </div>
        ))}
        <div className="field compact">
          <label>
            Expression
            <input name="expression" defaultValue={query.expression ?? ""} placeholder="smile" />
          </label>
        </div>
        <div className="field compact">
          <label>
            With character
            <input name="with_character" defaultValue={query.with_character ?? ""} placeholder="name" />
          </label>
        </div>
        <label className="check">
          <input type="checkbox" name="ranked" value="true" defaultChecked={query.ranked === "true"} /> Rank for this need
        </label>
        <button className="button small primary" type="submit">
          Show
        </button>
      </form>

      <section className="block" aria-label="Observations">
        <div className="block-head">
          <h2>
            {filters.ranked === "true" ? "Ranked for this need" : "Observations"} <small>{list.total}</small>
          </h2>
        </div>
        {list.observations.length ? (
          <div className="ref-grid">
            {list.observations.map((o) => (
              <div key={o.id} className="stack surface panel" style={{ padding: 8 }}>
                <ObservationCard observation={o} />
                <ObservationReview observation={o} />
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">No observations match. Use “Find observations in the Vault” on the character page.</p>
        )}
        {filters.ranked !== "true" && list.total > limit ? (
          <div className="row" style={{ marginTop: 14 }}>
            {offset > 0 ? (
              <Link className="button small ghost" href={pageHref(Math.max(0, offset - limit))}>
                ← Previous
              </Link>
            ) : null}
            <span className="hint">
              {offset + 1}-{Math.min(list.total, offset + limit)} of {list.total}
            </span>
            {offset + limit < list.total ? (
              <Link className="button small ghost" href={pageHref(offset + limit)}>
                Next →
              </Link>
            ) : null}
          </div>
        ) : null}
      </section>
    </>
  );
}
