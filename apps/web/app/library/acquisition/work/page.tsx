import Link from "next/link";
import { ApiUnreachableError, type MediaUnit, type WorkMedia, media } from "@/lib/api";
import {
  classLabel,
  dash,
  formatBytes,
  numberRanges,
  plural,
  relationLabel,
  seasonLabel,
} from "@/lib/acquisition";
import { ApiDown, Empty, StateChip } from "../_components/ui";

export const dynamic = "force-dynamic";

function unitMeta(unit: MediaUnit): string {
  const parts: string[] = [];
  if (unit.view === "pages") {
    parts.push(plural(unit.pages, "page"));
    if (unit.chapter_text && unit.label !== `Chapters ${unit.chapter_text}`) {
      parts.push(`ch ${dash(unit.chapter_text)}`);
    }
  }
  if (unit.view === "bundle") {
    parts.push(`archive · ${plural(unit.contained_videos, "video")} inside`);
  }
  if (unit.view === "video" && unit.plays_in_browser === "maybe") parts.push("plays if the browser supports its codecs");
  if (unit.view === "none") parts.push("preview not supported yet");
  parts.push(formatBytes(unit.size_bytes));
  return parts.join(" · ");
}

function action(unit: MediaUnit): string {
  switch (unit.view) {
    case "pages":
      return "Read";
    case "video":
      return "Play";
    case "document":
      return "Open";
    case "bundle":
      return "See inside";
    default:
      return "Details";
  }
}

/** Contained episodes grouped per season, for a bundle row. */
function bundleSummary(unit: MediaUnit): string {
  const bySeason = new Map<string, number[]>();
  for (const video of unit.contained) {
    if (video.episode === null) continue;
    const key = seasonLabel(video.season);
    bySeason.set(key, [...(bySeason.get(key) ?? []), video.episode]);
  }
  return [...bySeason.entries()].map(([season, eps]) => `${season} ${numberRanges(eps)}`).join(" · ");
}

/**
 * One work, as the files you can open. Units come from the acquisition
 * engine's own record of which files make up the work; each is addressed by
 * an opaque id, never by where it lives.
 */
export default async function WorkPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string; family?: string; material?: string }>;
}) {
  const params = await searchParams;
  let data: WorkMedia | null = null;
  let error: string | null = null;
  let missing = false;
  try {
    if (params.id) data = await media.forWork(params.id);
    else if (params.family && params.material) data = await media.unmatched(params.family, params.material);
    else missing = true;
  } catch (cause) {
    if (cause instanceof ApiUnreachableError) error = cause.message;
    else missing = true;
  }

  if (!data) {
    return (
      <>
        <Link className="crumb" href="/library/acquisition/families">
          ← Families
        </Link>
        {error ? (
          <ApiDown message={error} />
        ) : (
          <Empty title="This work isn't in the Library">
            <p>{missing ? "It may have been renamed or removed since the last scan." : ""}</p>
          </Empty>
        )}
      </>
    );
  }

  const familyHref = data.family_id
    ? `/library/acquisition/families/${encodeURIComponent(data.family_id)}`
    : "/library/acquisition/families";
  const videos = data.units.filter((u) => u.view === "video").length;
  const pages = data.units.reduce((n, u) => n + (u.view === "pages" ? u.pages : 0), 0);
  const bundled = data.units.reduce((n, u) => n + u.contained_videos, 0);

  return (
    <>
      <Link className="crumb" href={familyHref}>
        ← {data.family_title || "Families"}
      </Link>
      <header className="detail-head">
        <div>
          <p className="eyebrow">
            {classLabel(data.material_class)}
            {data.relation ? ` · ${relationLabel(data.relation)}` : ""}
          </p>
          <h1 className="title">{data.title}</h1>
          <div className="chips" style={{ marginTop: 14 }}>
            <StateChip state={data.state} />
            {data.unmapped ? <span className="chip quiet">Not matched to a work yet</span> : null}
          </div>
        </div>
        <div className="detail-facts">
          <div className="figure">
            <span className="n tabular">{data.units.length}</span>
            <span className="l">{data.units.length === 1 ? "file" : "files"}</span>
          </div>
          {pages ? (
            <div className="figure">
              <span className="n tabular">{pages}</span>
              <span className="l">pages</span>
            </div>
          ) : null}
          {videos || bundled ? (
            <div className="figure">
              <span className="n tabular">{videos + bundled}</span>
              <span className="l">{bundled ? "video files, incl. inside archives" : "video files"}</span>
            </div>
          ) : null}
        </div>
      </header>

      {!data.available ? (
        <div className="banner" role="status">
          <p>
            <strong>These files can&apos;t be opened right now.</strong> {data.reason}
          </p>
          <Link className="button small" href="/settings/diagnostics">
            Diagnostics
          </Link>
        </div>
      ) : null}

      {data.units.length ? (
        <div className="list">
          {data.units.map((unit) => (
            <div className="list-item" key={unit.id}>
              <div style={{ minWidth: 0 }}>
                <h3>{unit.label}</h3>
                <p className="sub">{unitMeta(unit)}</p>
                {unit.view === "bundle" && unit.contained.length ? (
                  <p className="sub">{bundleSummary(unit) || plural(unit.contained.length, "video")}</p>
                ) : null}
              </div>
              <div className="side">
                {data.available ? (
                  <Link
                    className={`button small${unit.view === "pages" || unit.view === "video" ? " primary" : ""}`}
                    href={`/view/${unit.id}`}
                  >
                    {action(unit)}
                  </Link>
                ) : (
                  <span className="muted">{action(unit)}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty title="No local files for this work">
          <p>{data.coverage_reason || "Nothing in the Vault is attributed to it yet."}</p>
        </Empty>
      )}
    </>
  );
}
