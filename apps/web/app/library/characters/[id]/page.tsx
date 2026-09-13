import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError, projects as projectsApi } from "@/lib/api";
import { type CharacterVault, type VaultCard, VaultNotFound, vault, words } from "@/lib/vault";
import { ApiDown, Empty } from "../../acquisition/_components/ui";
import { OriginChip, RefCard } from "../../_vault/parts";
import { AddOutfit, EditCharacter } from "../CharacterForms";

export const dynamic = "force-dynamic";

function Cards({ cards }: { cards: VaultCard[] }) {
  return (
    <div className="ref-grid small">
      {cards.map((card) => (
        <RefCard
          key={card.link_id}
          reference={card.reference}
          href={`/library/references/${card.reference.id}`}
          note={card.preferred ? "Preferred" : undefined}
        />
      ))}
    </div>
  );
}

function Group({ title, groups, empty }: { title: string; groups: Record<string, VaultCard[]>; empty: string }) {
  const entries = Object.entries(groups).filter(([, cards]) => cards.length);
  return (
    <section className="block" aria-label={title}>
      <div className="block-head">
        <h2>{title}</h2>
      </div>
      {entries.length ? (
        <div className="stack">
          {entries.map(([aspect, cards]) => (
            <div key={aspect} className="stack">
              <span className="eyebrow" style={{ margin: 0 }}>
                {words(aspect)} <span className="muted">· {cards.length}</span>
              </span>
              <Cards cards={cards} />
            </div>
          ))}
        </div>
      ) : (
        <p className="hint">{empty}</p>
      )}
    </section>
  );
}

/**
 * One character's vault: identity (face, hair, body, marks), wardrobe (outfits
 * with their references), acting (expressions, poses), where the references
 * come from, and what each project treats as canonical.
 */
export default async function CharacterVaultPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) notFound();
  let data: CharacterVault | null = null;
  let error: string | null = null;
  try {
    data = await vault.character(id);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!data) return <ApiDown service="reference vault" message={error ?? "no response"} />;
  const projects = (await projectsApi.list().catch(() => [])).map((p) => ({ id: p.id, title: p.title }));
  const { character } = data;

  return (
    <>
      <Link className="crumb" href="/library/characters">
        ← Characters
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">{words(character.subject_kind)} vault</p>
          <h1 className="title">{character.display_name}</h1>
          <p className="lead">
            {character.summary || "Add references while reading: select a face, an outfit or a pose and add it here."}
          </p>
          <div className="row" style={{ marginTop: 12 }}>
            <span className="chip quiet">{data.reference_count} references</span>
            {Object.entries(data.sources).map(([origin, count]) => (
              <span key={origin} className="row" style={{ gap: 4 }}>
                <OriginChip origin={origin} tiny />
                <span className="muted tabular">{count}</span>
              </span>
            ))}
          </div>
        </div>
      </header>

      {data.preferred.length ? (
        <section aria-label="Preferred">
          <div className="block-head">
            <h2>Preferred</h2>
          </div>
          <Cards cards={data.preferred} />
        </section>
      ) : null}

      <Group title="Identity" groups={data.identity} empty="No face, hair, body or marks yet." />

      <section className="block" aria-label="Wardrobe">
        <div className="block-head">
          <h2>Wardrobe</h2>
        </div>
        <div className="stack">
          {data.wardrobe.outfits.map((outfit) => (
            <div key={outfit.id} className="surface panel stack">
              <div className="spread">
                <h3 style={{ margin: 0 }}>{outfit.name}</h3>
                <span className="row">
                  <span className="chip quiet tiny">{words(outfit.kind)}</span>
                  {outfit.project_key ? <span className="chip accent plain tiny">{outfit.project_key}</span> : null}
                </span>
              </div>
              <p className="hint">
                {[outfit.era, outfit.season_weather, outfit.condition].filter(Boolean).join(" · ") || "No era, season or condition noted."}
              </p>
              {outfit.references.length ? (
                <Cards cards={outfit.references} />
              ) : (
                <p className="hint">No references for this outfit yet.</p>
              )}
            </div>
          ))}
          {data.wardrobe.unassigned.length ? (
            <div className="stack">
              <span className="eyebrow" style={{ margin: 0 }}>
                Wardrobe references without an outfit
              </span>
              <Cards cards={data.wardrobe.unassigned} />
            </div>
          ) : null}
          <AddOutfit characterId={character.id} projects={projects} />
        </div>
      </section>

      <Group title="Acting" groups={data.acting} empty="No expressions, poses or gestures yet." />

      <section className="block" aria-label="Projects">
        <div className="block-head">
          <h2>In projects</h2>
        </div>
        {Object.keys(data.project_standing).length || data.scoped_visual_modes.length ? (
          <div className="list">
            {Object.entries(data.project_standing).map(([project, standings]) => (
              <div className="list-item" key={project}>
                <div>
                  <h3>{project}</h3>
                  <p className="sub">
                    {Object.entries(standings)
                      .map(([standing, refs]) => `${words(standing)}: ${refs.length}`)
                      .join(" · ")}
                  </p>
                </div>
              </div>
            ))}
            {data.scoped_visual_modes.map((m) => (
              <div className="list-item" key={m.assignment_id}>
                <div>
                  <h3>
                    {m.visual_mode.name} <span className="muted">· {words(m.visual_mode.category)}</span>
                  </h3>
                  <p className="sub">
                    {m.project_key} · {words(m.scope)}
                    {m.episode ? ` ${m.episode}` : ""}
                    {m.event_label ? ` · ${m.event_label}` : ""} · {words(m.trigger)}
                  </p>
                </div>
                <span className="side muted">Mode, not identity</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="Not in any project yet">
            <p>Mark references as canonical or preferred for a project, or give this character a scoped visual mode.</p>
          </Empty>
        )}
      </section>

      <section className="block">
        <EditCharacter character={character} />
      </section>
    </>
  );
}
