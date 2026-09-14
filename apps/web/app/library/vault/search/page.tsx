import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { type SearchResults, catalog } from "@/lib/catalog";
import { plural } from "@/lib/acquisition";
import { words } from "@/lib/vault";
import { ApiDown, Empty, PageHead } from "../../acquisition/_components/ui";
import { SearchBox, UnitRow } from "../_parts";

export const dynamic = "force-dynamic";

/** One box across the studio: Vault units, references, Inbox, project documents and music. */
export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const query = q.trim().slice(0, 200);
  let results: SearchResults | null = null;
  let error: string | null = null;
  if (query) {
    try {
      results = await catalog.search(query);
    } catch (cause) {
      error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
    }
  }
  const count = results
    ? results.units.total + results.references.length + results.candidates.length + results.documents.length + results.music.length
    : 0;

  return (
    <>
      <PageHead eyebrow="Studio" title="Search" lead="Series, chapters, episodes, file names, creators, collections, references, Inbox items, project documents and music notes." />
      {error ? <ApiDown service="catalog" message={error} /> : null}
      <SearchBox q={query} />
      {results && !count ? (
        <Empty title="Nothing matches">
          <p>Try fewer words, a known alternative title, or a creator handle without the @.</p>
        </Empty>
      ) : null}
      {results?.units.total ? (
        <section>
          <div className="section-title">
            <h2>In the Vault · {plural(results.units.total, "result")}</h2>
          </div>
          <div className="unit-list">
            {results.units.units.map((unit) => (
              <UnitRow key={unit.id} unit={unit} showSeries />
            ))}
          </div>
        </section>
      ) : null}
      {results?.references.length ? (
        <section>
          <div className="section-title">
            <h2>References · {results.references.length}</h2>
          </div>
          <div className="list surface">
            {results.references.map((r) => (
              <div key={r.id} className="list-item">
                <div>
                  <h3>
                    <Link href={`/library/references/${r.id}`}>{r.label || words(r.reference_class)}</Link>
                  </h3>
                  <p className="sub">
                    {words(r.origin)} · {words(r.reference_class)}
                    {r.collection ? ` · ${r.collection}` : ""}
                    {r.creator_handle ? ` · ${r.creator_handle}` : ""} · rights {words(r.rights_status)} · training{" "}
                    {words(r.training_eligibility)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {results?.candidates.length ? (
        <section>
          <div className="section-title">
            <h2>Inbox · {results.candidates.length}</h2>
          </div>
          <div className="list surface">
            {results.candidates.map((c) => (
              <div key={c.id} className="list-item">
                <div>
                  <h3>
                    <Link href={`/library/inbox?status=${c.status}`}>{c.display_name || c.id}</Link>
                  </h3>
                  <p className="sub">
                    {words(c.intake_kind)} · {words(c.status)}
                    {c.collection ? ` · ${c.collection}` : ""}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {results?.documents.length ? (
        <section>
          <div className="section-title">
            <h2>Project documents · {results.documents.length}</h2>
          </div>
          <div className="list surface">
            {results.documents.map((d) => (
              <div key={`${d.project_id}-${d.id}`} className="list-item">
                <div>
                  <h3>
                    <Link href={`/projects/${d.project_id}/documents/${d.id}`}>{d.title}</Link>
                  </h3>
                  <p className="sub">
                    {d.project_title} · {words(d.lifecycle)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      {results?.music.length ? (
        <section>
          <div className="section-title">
            <h2>Music notes · {results.music.length}</h2>
          </div>
          <div className="list surface">
            {results.music.map((m) => (
              <div key={m.id} className="list-item">
                <div>
                  <h3>{m.track}</h3>
                  <p className="sub">
                    {m.artist} · <Link href={`/projects/${m.project_key}`}>{m.project_key}</Link>
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
