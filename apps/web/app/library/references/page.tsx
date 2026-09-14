import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import {
  REFERENCE_CLASSES,
  REFERENCE_USES,
  type ReferenceView,
  USER_ORIGINS,
  vault,
  words,
} from "@/lib/vault";
import { ApiDown, Empty, PageHead } from "../acquisition/_components/ui";
import { RefCard } from "../_vault/parts";

export const dynamic = "force-dynamic";

type Search = Record<string, string | undefined>;

function hrefWith(current: Search, key: string, value: string | null): string {
  const next = new URLSearchParams();
  for (const [k, v] of Object.entries(current)) if (v && k !== key) next.set(k, v);
  if (value) next.set(key, value);
  const text = next.toString();
  return `/library/references${text ? `?${text}` : ""}`;
}

function Filter({
  label,
  name,
  values,
  current,
}: {
  label: string;
  name: string;
  values: readonly string[];
  current: Search;
}) {
  return (
    <>
      <span className="toolbar-label">{label}</span>
      <nav className="segmented" aria-label={label}>
        <Link href={hrefWith(current, name, null)} data-active={!current[name]}>
          All
        </Link>
        {values.map((value) => (
          <Link key={value} href={hrefWith(current, name, value)} data-active={current[name] === value}>
            {words(value)}
          </Link>
        ))}
      </nav>
    </>
  );
}

/**
 * Every catalogued reference: pages and regions of held manga, captured
 * frames, official art, fan art and approved project work - filterable by
 * what it is and what it is for.
 */
export default async function ReferencesPage({ searchParams }: { searchParams: Promise<Search> }) {
  const current = await searchParams;
  const filters: Search = {
    reference_class: current.class,
    origin: current.origin,
    use: current.use,
  };
  let references: ReferenceView[] = [];
  let error: string | null = null;
  try {
    references = await vault.references(filters);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  return (
    <>
      <PageHead
        eyebrow="Reference vault"
        title="References"
        lead="Pages and regions of your manga, frames, official art, fan art and approved project work - each named by content and leading back to where it came from. Removing one never touches the original."
        aside={
          <Link className="button" href="/library/inbox">
            Open the inbox
          </Link>
        }
      />
      {error ? <ApiDown service="reference vault" message={error} /> : null}

      <div className="toolbar">
        <Filter label="Class" name="class" values={REFERENCE_CLASSES} current={current} />
      </div>
      <div className="toolbar">
        <Filter
          label="Origin"
          name="origin"
          values={[...USER_ORIGINS, "PROJECT_APPROVED"]}
          current={current}
        />
      </div>
      <div className="toolbar">
        <Filter label="Use" name="use" values={REFERENCE_USES} current={current} />
      </div>

      {references.length ? (
        <div className="ref-grid">
          {references.map((reference) => (
            <RefCard
              key={reference.id}
              reference={reference}
              href={`/library/references/${reference.id}`}
              note={reference.characters.map((c) => `${c.character_name} · ${words(c.aspect)}`)[0]}
            />
          ))}
        </div>
      ) : error ? null : (
        <Empty title="No references match">
          <p>
            Open a manga in the viewer and use <b>Add reference</b>, or bring images, links, clips
            and screenshots in through the inbox.
          </p>
        </Empty>
      )}
    </>
  );
}
