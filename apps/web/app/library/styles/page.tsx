import { ApiUnreachableError, projects as projectsApi } from "@/lib/api";
import { type ModeAssignment, type StyleVault, vault, words } from "@/lib/vault";
import { ApiDown, Empty, PageHead } from "../acquisition/_components/ui";
import { RefCard } from "../_vault/parts";
import { AssignMode, CreateMode, RemoveAssignment } from "./StyleForms";

export const dynamic = "force-dynamic";

function scopeText(a: ModeAssignment): string {
  switch (a.scope) {
    case "EPISODE":
      return `Episode ${a.episode}`;
    case "SCENE":
      return `${a.episode} · scene ${a.scene}`;
    case "SEQUENCE":
      return `${a.episode} · pages ${a.page_from}-${a.page_to}`;
    case "PANEL":
      return `${a.episode} · page ${a.page_from} panel ${a.panel}`;
    default:
      return `Event: ${a.event_label}`;
  }
}

/**
 * The Style Vault: technique references - real manga pages and panels among
 * them - organised by visual mode and by what they teach. Styles never
 * belong to a character; a project applies a mode to a scope instead.
 */
export default async function StylesPage() {
  let styles: StyleVault | null = null;
  let error: string | null = null;
  try {
    styles = await vault.styles();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const [projects, characters] = await Promise.all([
    projectsApi.list().catch(() => []),
    vault.characters().catch(() => []),
  ]);
  const assignments = await Promise.all(
    projects.map(async (p) => ({ project: p, rows: await vault.assignments(p.id).catch(() => []) })),
  );
  const modes = styles?.modes ?? [];
  const modeName = new Map(modes.map((m) => [m.id, m.name]));
  const characterName = new Map(characters.map((c) => [c.id, c.display_name]));

  return (
    <>
      <PageHead
        eyebrow="Reference vault"
        title="Styles & modes"
        lead="How a moment is drawn - intimate night, expressive comedy, comic squash, threat, memory haze - kept apart from who is drawn. A project applies a mode to a panel, a scene, a run of pages, an episode or an event."
      />
      {error ? <ApiDown service="reference vault" message={error} /> : null}

      <section aria-label="Visual modes">
        <div className="block-head">
          <h2>
            Visual modes <small>{modes.length}</small>
          </h2>
        </div>
        {modes.length ? (
          <div className="stack">
            {modes.map((mode) => (
              <div className="surface panel stack" key={mode.id}>
                <div className="spread">
                  <h3 style={{ margin: 0 }}>{mode.name}</h3>
                  <span className="chip quiet">{words(mode.category)}</span>
                </div>
                {mode.description ? <p className="soft" style={{ margin: 0 }}>{mode.description}</p> : null}
                {mode.references.length ? (
                  <div className="ref-grid small">
                    {mode.references.map((card) => (
                      <RefCard
                        key={`${card.reference.id}-${card.facet}`}
                        reference={card.reference}
                        href={`/library/references/${card.reference.id}`}
                        note={words(card.facet)}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="hint">No technique references for this mode yet - add some from the reader.</p>
                )}
              </div>
            ))}
          </div>
        ) : error ? null : (
          <Empty title="No visual modes yet">
            <p>Create the modes your project switches between.</p>
          </Empty>
        )}
        <div style={{ marginTop: 16 }}>
          <CreateMode />
        </div>
      </section>

      <section className="block" aria-label="By technique">
        <div className="block-head">
          <h2>By technique</h2>
        </div>
        {styles && Object.keys(styles.by_facet).length ? (
          <div className="stack">
            {Object.entries(styles.by_facet).map(([facet, cards]) => (
              <div className="stack" key={facet}>
                <span className="eyebrow" style={{ margin: 0 }}>
                  {words(facet)} <span className="muted">· {cards.length}</span>
                </span>
                <div className="ref-grid small">
                  {cards.map((card) => (
                    <RefCard key={`${facet}-${card.reference.id}`} reference={card.reference} href={`/library/references/${card.reference.id}`} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">Technique references appear here by what they teach.</p>
        )}
      </section>

      <section className="block" aria-label="Project modes">
        <div className="block-head">
          <h2>Modes in projects</h2>
        </div>
        {assignments.some((a) => a.rows.length) ? (
          <div className="list" style={{ marginBottom: 16 }}>
            {assignments.flatMap(({ project, rows }) =>
              rows.map((a) => (
                <div className="list-item" key={a.id}>
                  <div>
                    <h3>
                      {modeName.get(a.visual_mode_id) ?? "Mode"} <span className="muted">· {project.title}</span>
                    </h3>
                    <p className="sub">
                      {scopeText(a)} · {words(a.trigger)}
                      {a.character_id ? ` · ${characterName.get(a.character_id) ?? "character"}` : ""}
                    </p>
                  </div>
                  <span className="side">
                    <RemoveAssignment project={project.id} id={a.id} />
                  </span>
                </div>
              )),
            )}
          </div>
        ) : null}
        <AssignMode
          modes={modes}
          projects={projects.map((p) => ({ id: p.id, title: p.title }))}
          characters={characters}
        />
      </section>
    </>
  );
}
