import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiUnreachableError,
  type FamilyDetail,
  type MaterialSummary,
  type SourceOut,
  type WorkRow,
  acquisition,
} from "@/lib/api";
import {
  RELATION_ORDER,
  classLabel,
  dash,
  formatBytes,
  plural,
  relationLabel,
  seasonLabel,
  timeAgo,
} from "@/lib/acquisition";
import { SourceSearch } from "../../_components/SourceSearch";
import { ApiDown, StateChip } from "../../_components/ui";

export const dynamic = "force-dynamic";

const MAIN = new Set(["MAIN_WORK", "SEQUEL", "PREQUEL"]);

function byRelation(a: WorkRow, b: WorkRow): number {
  const rank = (w: WorkRow) => {
    const i = RELATION_ORDER.indexOf(w.relation ?? "UNKNOWN");
    return i === -1 ? RELATION_ORDER.length : i;
  };
  return rank(a) - rank(b) || a.title.localeCompare(b.title);
}

function chapterFacts(work: WorkRow): React.ReactNode[] {
  const facts: React.ReactNode[] = [];
  if (work.chapters && work.chapter_min !== null && work.chapter_max !== null) {
    const total =
      work.source_chapter_count ??
      (work.remote_latest_chapter ? Math.round(work.remote_latest_chapter) : null);
    facts.push(
      <span key="ch">
        {total && work.chapters <= total
          ? `${work.chapters} of ${total} chapters`
          : `${work.chapters} chapters`}{" "}
        · ch{" "}
        {work.chapter_min}–{work.chapter_max}
      </span>,
    );
  }
  if (work.missing_chapters) {
    facts.push(
      <span key="miss" className="gap">
        missing ch {dash(work.missing_chapters)}
      </span>,
    );
  } else if (work.gaps && work.coverage_status === "COMPLETE") {
    facts.push(<span key="skip">numbering skips {dash(work.gaps)}, nothing missing</span>);
  } else if (work.gaps) {
    facts.push(
      <span key="gaps" className="gap">
        gaps at {dash(work.gaps)}
      </span>,
    );
  }
  return facts;
}

function WorkItem({ work, sources }: { work: WorkRow; sources: SourceOut[] }) {
  const facts: React.ReactNode[] = [];
  if (work.local_files) {
    facts.push(
      <span key="files">
        {work.media === "video"
          ? plural(work.local_files, "video file")
          : plural(work.local_files, "file")}
        {work.local_bytes ? ` · ${formatBytes(work.local_bytes)}` : ""}
      </span>,
    );
  }
  facts.push(...chapterFacts(work));
  if (work.last_added_at && work.local_files) {
    facts.push(<span key="added">added {timeAgo(work.last_added_at)}</span>);
  }

  const wantsSource = work.state === "MISSING" || work.state === "PARTIAL";
  return (
    <article className="work">
      <div className="work-title">
        <h3>{work.title}</h3>
        <span className={`relation${work.relation && MAIN.has(work.relation) ? " main" : ""}`}>
          {relationLabel(work.relation)}
        </span>
        {work.origin === "vault-adopted" || work.review_required ? (
          <span className="chip quiet">Needs review</span>
        ) : null}
      </div>
      <div>
        <StateChip state={work.state} />
      </div>

      {facts.length ? <div className="work-facts">{facts}</div> : null}

      {work.episodes.length || work.other_videos ? (
        <div className="seasons" aria-label="Episodes held">
          {work.episodes.map((run) => (
            <span key={`${run.season}`} className="season">
              <b>{seasonLabel(run.season)}</b> {dash(run.episodes_text)}
              {run.gaps_text ? <span className="gap">· missing {dash(run.gaps_text)}</span> : null}
            </span>
          ))}
          {work.other_videos ? (
            <span className="season">
              <b>{plural(work.other_videos, "other video")}</b> no episode number
            </span>
          ) : null}
        </div>
      ) : null}

      {work.state === "NEEDS_MAPPING" ? (
        <p className="work-note">
          {plural(work.unmapped_local_files, "local file")} of this kind{" "}
          {work.unmapped_local_files === 1 ? "is" : "are"} in the family folder but not matched to a
          work, so this is not called missing.
        </p>
      ) : work.state === "STALE" ? (
        <p className="work-note">
          The folder changed after the last scan. Refresh to know whether this is here.
        </p>
      ) : work.state === "PRESENT" ? (
        <p className="work-note">
          In your Library. Nothing is known to compare against, so completeness is not verified.
        </p>
      ) : work.state === "PARTIAL" && !work.missing_chapters && work.coverage_reason ? (
        <p className="work-note">{work.coverage_reason}</p>
      ) : null}

      <details className="disclosure">
        <summary>{wantsSource ? "Details and sources" : "Details"}</summary>
        <div className="disclosure-body">
          {work.aliases.length ? (
            <p style={{ margin: "0 0 6px" }}>Also known as {work.aliases.slice(0, 6).join(" · ")}</p>
          ) : null}
          <p style={{ margin: "0 0 6px" }}>
            {work.official === true
              ? "Official"
              : work.official === false
                ? "Not official"
                : "Official status not verified"}
            {work.confidence ? ` · ${work.confidence} confidence` : ""}
            {work.languages.length ? ` · ${work.languages.join(", ")}` : ""}
            {work.coverage_reason ? ` · ${work.coverage_reason}` : ""}
          </p>
          {work.local_path || work.expected_path ? (
            <p style={{ margin: 0 }}>
              <code>{work.local_path ?? work.expected_path}</code>
              {!work.folder_exists ? <span className="muted"> · no folder yet</span> : null}
            </p>
          ) : null}
          {wantsSource ? (
            <SourceSearch
              titles={work.search_titles}
              sources={sources}
              missing={work.missing_chapters}
            />
          ) : null}
        </div>
      </details>
    </article>
  );
}

function MaterialBlock({
  material,
  works,
  sources,
}: {
  material: MaterialSummary;
  works: WorkRow[];
  sources: SourceOut[];
}) {
  return (
    <section className="material-block" aria-labelledby={`m-${material.material_class}`}>
      <header>
        <h2 id={`m-${material.material_class}`}>{classLabel(material.material_class)}</h2>
        <div className="facts">
          {material.files ? (
            <span className="tabular">
              {material.video_files
                ? plural(material.video_files, "video file")
                : plural(material.files, "file")}{" "}
              · {formatBytes(material.bytes)}
            </span>
          ) : null}
          <StateChip state={material.state} />
        </div>
      </header>
      {[...works].sort(byRelation).map((work) => (
        <WorkItem key={work.id} work={work} sources={sources} />
      ))}
      {material.unmapped_files ? (
        <p className="mapping-note">
          {plural(material.unmapped_files, "local file")} in this folder{" "}
          {material.unmapped_files === 1 ? "is" : "are"} not matched to any work yet.{" "}
          <Link href="/library/acquisition/intake#mapping">Review uncatalogued material →</Link>
        </p>
      ) : null}
    </section>
  );
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
    if (cause instanceof ApiUnreachableError) error = cause.message;
    else if (String(cause).includes("404")) notFound();
    else error = String(cause);
  }

  if (!data) {
    return (
      <>
        <Link className="crumb" href="/library/acquisition/families">
          ← Families
        </Link>
        <ApiDown message={error ?? "no response"} />
      </>
    );
  }

  const { family, works } = data;
  const byClass = new Map<string, WorkRow[]>();
  for (const work of works) {
    const key = (work.material_class ?? "other").toLowerCase();
    byClass.set(key, [...(byClass.get(key) ?? []), work]);
  }
  const story = family.materials.filter((m) => m.story);
  const supplements = family.materials.filter((m) => !m.story);
  const supplementsHeld = supplements.some(
    (m) => m.complete + m.partial + m.present > 0 || m.files > 0,
  );

  return (
    <>
      <Link className="crumb" href="/library/acquisition/families">
        ← Families
      </Link>

      <header className="detail-head">
        <div>
          <p className="eyebrow">Family</p>
          <h1 className="title xl">{family.title}</h1>
          <div className="chips" style={{ marginTop: 16 }}>
            <StateChip state={family.state} />
            {family.stale ? <StateChip state="STALE" /> : null}
            {family.review_status !== "ACCEPTED" ? (
              <span className="chip quiet">New to the catalogue</span>
            ) : null}
          </div>
        </div>
        <div className="detail-facts">
          <div className="figure">
            <span className="n">{formatBytes(family.bytes)}</span>
            <span className="l">{plural(family.files, "file")}</span>
          </div>
          <div className="figure">
            <span className="n tabular">
              {family.story_held}/{family.story_works || family.works_total}
            </span>
            <span className="l">story works held</span>
          </div>
          <div className="figure">
            <span className="n" style={{ fontSize: 20, lineHeight: "41px" }}>
              {timeAgo(family.last_added_at)}
            </span>
            <span className="l">last added</span>
          </div>
        </div>
      </header>

      {story.map((material) => (
        <MaterialBlock
          key={material.material_class}
          material={material}
          works={byClass.get(material.material_class) ?? []}
          sources={sources}
        />
      ))}

      {supplements.length ? (
        <details className="supplements block" open={supplementsHeld}>
          <summary className="block-head">
            <h2>
              Supplements
              <small>
                {family.supplements_held} of {family.supplements} held · official, but not the story
                itself
              </small>
            </h2>
            <span className="toggle" />
          </summary>
          {supplements.map((material) => (
            <MaterialBlock
              key={material.material_class}
              material={material}
              works={byClass.get(material.material_class) ?? []}
              sources={sources}
            />
          ))}
        </details>
      ) : null}

      {!family.materials.length ? (
        <div className="empty" style={{ marginTop: 30 }}>
          <h3>Nothing catalogued in this family yet</h3>
          <p>A catalogue refresh looks up what officially exists for it.</p>
        </div>
      ) : null}

      <details className="disclosure block">
        <summary>Where this family lives</summary>
        <div className="disclosure-body">
          <code>{family.path}</code> <span className="muted">· read-only to Continuum</span>
          {family.aliases.length ? (
            <p style={{ margin: "8px 0 0" }}>Also known as {family.aliases.join(" · ")}</p>
          ) : null}
        </div>
      </details>
    </>
  );
}
