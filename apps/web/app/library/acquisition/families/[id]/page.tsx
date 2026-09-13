import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiUnreachableError,
  type FamilyDetail,
  type SourceOut,
  type WorkRow,
  acquisition,
} from "@/lib/api";
import { RELATION_ORDER, classLabel, formatBytes, plural } from "@/lib/acquisition";
import {
  ApiDown,
  Empty,
  Meter,
  MeterLegend,
  Pill,
  Stat,
  WorkLine,
} from "../../_components/ui";

export const dynamic = "force-dynamic";

/** Material class order: story first, then supplements, then fan material. */
const CLASS_ORDER = [
  "manga",
  "manhwa",
  "manhua",
  "light-novel",
  "web-novel",
  "anime",
  "guidebook",
  "fanbook",
  "art-book",
  "visual-reference",
  "colored-edition",
  "special",
  "anthology",
  "official-doujin",
  "other-official",
  "fan-art",
  "fan-work",
];

function groupByClass(works: WorkRow[]): [string, WorkRow[]][] {
  const groups = new Map<string, WorkRow[]>();
  for (const work of works) {
    const key = work.material_class ?? "other";
    const list = groups.get(key);
    if (list) list.push(work);
    else groups.set(key, [work]);
  }
  return [...groups.entries()].sort((a, b) => {
    const rank = (key: string) => {
      const index = CLASS_ORDER.indexOf(key);
      return index === -1 ? CLASS_ORDER.length : index;
    };
    return rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]);
  });
}

function byRelation(a: WorkRow, b: WorkRow): number {
  const rank = (work: WorkRow) => {
    const index = RELATION_ORDER.indexOf(work.relation ?? "UNKNOWN");
    return index === -1 ? RELATION_ORDER.length : index;
  };
  return rank(a) - rank(b) || a.title.localeCompare(b.title);
}

export default async function FamilyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let data: FamilyDetail | null = null;
  let sources: SourceOut[] = [];
  let error: string | null = null;
  try {
    const [detail, registry] = await Promise.all([acquisition.family(id), acquisition.sources()]);
    data = detail;
    sources = registry.sources;
  } catch (cause) {
    if (cause instanceof ApiUnreachableError) {
      error = cause.message;
    } else if (String(cause).includes("404")) {
      notFound();
    } else {
      error = `Unexpected error: ${String(cause)}`;
    }
  }

  if (error) {
    return (
      <main>
        <p className="crumb">
          <Link href="/library/acquisition/families">← Families</Link>
        </p>
        <ApiDown message={error} />
      </main>
    );
  }
  if (!data) return null;

  const { family, works, findings } = data;
  const grouped = groupByClass(works);
  const missingFolders = works.filter((work) => work.layout_status === "MISSING_FOLDER");

  return (
    <main>
      <p className="crumb">
        <Link href="/library/acquisition/families">← Families</Link>
      </p>
      <p className="eyebrow">Source family</p>
      <h1 className="headline">{family.title}</h1>
      <p className="lede">
        {plural(family.works_total, "catalogued work")} across{" "}
        {plural(family.classes.length, "kind")} of material. Official
        is not the same as main canon, so each kind is listed on its own.
      </p>

      <div className="stats">
        <Stat label="complete" value={family.complete} tone="ok" />
        <Stat label="partial" value={family.partial} tone="warn" />
        <Stat label="missing" value={family.missing} tone="err" />
        <Stat label="unverified" value={family.unknown} />
        <Stat label="files" value={family.files} />
        <Stat label="on disk" value={formatBytes(family.bytes)} />
      </div>
      <div style={{ marginTop: 16 }}>
        <Meter
          complete={family.complete}
          partial={family.partial}
          missing={family.missing}
          unknown={family.unknown}
        />
        <MeterLegend />
      </div>
      <div className="pills" style={{ marginTop: 14 }}>
        {family.category ? <Pill>{family.category.toLowerCase()}</Pill> : null}
        {family.medium ? <Pill>{classLabel(family.medium)}</Pill> : null}
        {family.review ? <Pill tone="warn">{family.review} to review</Pill> : null}
        {family.folder_exists ? null : <Pill tone="err">folder not present</Pill>}
      </div>
      <details className="finder provenance">
        <summary>Where this family lives</summary>
        <dl className="kv">
          <dt>Folder</dt>
          <dd>
            <code>{family.path}</code>{" "}
            <span className="row-meta">read-only to Continuum</span>
          </dd>
          {family.aliases.length ? (
            <>
              <dt>Also known as</dt>
              <dd>{family.aliases.join(" · ")}</dd>
            </>
          ) : null}
        </dl>
      </details>

      {missingFolders.length ? (
        <div className="notice" style={{ marginTop: 18 }}>
          <strong>{plural(missingFolders.length, "folder")} missing.</strong>
          <p style={{ margin: "6px 0 0", fontSize: 13 }}>
            Continuum never writes to the Vault. The{" "}
            <Link href="/library/acquisition">overview</Link> shows the exact command that would
            create them, for you to run.
          </p>
        </div>
      ) : null}

      {grouped.map(([materialClass, list]) => (
        <section key={materialClass}>
          <div className="section">
            <h2>{classLabel(materialClass)}</h2>
            <span className="hint">{plural(list.length, "work")}</span>
          </div>
          <div className="rows">
            {[...list].sort(byRelation).map((work) => (
              <WorkLine key={work.id} work={work} sources={sources} />
            ))}
          </div>
        </section>
      ))}

      {!works.length ? (
        <Empty title="No works catalogued in this family">
          <p>Run a discovery pass to find what officially exists.</p>
        </Empty>
      ) : null}

      {findings.length ? (
        <>
          <div className="section">
            <h2>Findings</h2>
            <span className="hint">observations, never actions</span>
          </div>
          <div className="rows">
            {findings.map((finding, index) => (
              <div className="row-item" key={index}>
                <div className="row-main">
                  <div className="row-title">
                    <Pill tone={String(finding.type) === "INFO" ? "muted" : "warn"}>
                      {String(finding.type ?? "note").replaceAll("_", " ").toLowerCase()}
                    </Pill>
                    <code style={{ fontSize: 12 }}>{String(finding.path ?? "")}</code>
                  </div>
                  <p className="row-meta">{String(finding.detail ?? "")}</p>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </main>
  );
}
