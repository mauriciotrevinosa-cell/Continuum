import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { type CharacterSummary, vault, words } from "@/lib/vault";
import { ApiDown, Empty, PageHead } from "../acquisition/_components/ui";
import { CreateCharacter } from "./CharacterForms";

export const dynamic = "force-dynamic";

/** Everyone - and everything - that can be drawn, each with its own vault. */
export default async function CharactersPage() {
  let characters: CharacterSummary[] = [];
  let error: string | null = null;
  try {
    characters = await vault.characters();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  return (
    <>
      <PageHead
        eyebrow="Reference vault"
        title="Characters"
        lead="Identity, wardrobe and acting, kept apart. A character's look can change with a project, an era or the weather; who they are does not."
      />
      {error ? <ApiDown service="reference vault" message={error} /> : null}
      {characters.length ? (
        <div className="list" style={{ marginBottom: 32 }}>
          {characters.map((c) => (
            <Link className="list-item" key={c.id} href={`/library/characters/${c.id}`}>
              <div>
                <h3>{c.display_name}</h3>
                <p className="sub">
                  {[c.subject_kind !== "CHARACTER" ? words(c.subject_kind) : "", c.source_label, c.summary]
                    .filter(Boolean)
                    .join(" · ") || "No notes yet"}
                </p>
              </div>
              <span className="side muted">Open vault →</span>
            </Link>
          ))}
        </div>
      ) : error ? null : (
        <div style={{ marginBottom: 32 }}>
          <Empty title="No characters yet">
            <p>Create one, then add references to it while reading.</p>
          </Empty>
        </div>
      )}
      <CreateCharacter />
    </>
  );
}
