import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiUnreachableError,
  type ArchiveListing,
  MEDIA_ID,
  type MediaDetail,
  media,
} from "@/lib/api";
import { classLabel, formatBytes, plural, seasonLabel } from "@/lib/acquisition";
import { Player } from "../Player";
import { Reader } from "../Reader";

export const dynamic = "force-dynamic";

/**
 * Opens one held file by its opaque id.
 *
 * Image archives read page by page, videos play in the browser's own player,
 * PDFs open inline, and an archive of videos shows what it contains - it is
 * never treated as an episode. Anything else is described honestly.
 */
export default async function ViewPage({ params }: { params: Promise<{ mediaId: string }> }) {
  const { mediaId } = await params;
  if (!MEDIA_ID.test(mediaId)) notFound();

  let detail: MediaDetail | null = null;
  let listing: ArchiveListing | null = null;
  let offline: string | null = null;
  try {
    detail = await media.detail(mediaId);
    if (detail.unit.view === "pages" || detail.unit.view === "bundle") {
      listing = await media.pages(mediaId);
    }
  } catch (cause) {
    if (cause instanceof ApiUnreachableError) offline = cause.message;
    else if (!detail) notFound();
  }

  if (!detail) {
    return (
      <div className="viewer-message">
        <div className="empty" role="alert">
          <h3>The Library service isn&apos;t reachable</h3>
          <p>Start it, then reload this page.</p>
          <details className="disclosure" style={{ marginTop: 14 }}>
            <summary>Details</summary>
            <div className="disclosure-body">
              <code>{offline}</code>
            </div>
          </details>
        </div>
      </div>
    );
  }

  const { unit } = detail;
  const workHref = detail.work_id
    ? `/library/acquisition/work?id=${encodeURIComponent(detail.work_id)}`
    : "/library/acquisition/families";
  const title = [detail.work_title, unit.label].filter(Boolean).join(" · ") || unit.name;
  const previousHref = detail.previous_id ? `/view/${detail.previous_id}` : null;
  const nextHref = detail.next_id ? `/view/${detail.next_id}` : null;

  if (unit.view === "pages" && listing && listing.pages.length) {
    return (
      <Reader
        mediaId={unit.id}
        total={listing.pages.length}
        chapters={listing.chapters}
        title={title}
        backHref={workHref}
        previousHref={previousHref}
        nextHref={nextHref}
      />
    );
  }

  const contained = [...(unit.contained.length ? unit.contained : (listing?.videos ?? []))].sort(
    (a, b) =>
      (a.season ?? 999) - (b.season ?? 999) ||
      (a.episode ?? 99999) - (b.episode ?? 99999) ||
      a.name.localeCompare(b.name),
  );

  return (
    <div className="viewer-page">
      <header className="viewer-bar">
        <Link href={workHref} className="crumb" style={{ margin: 0 }}>
          ← {detail.work_title || "Library"}
        </Link>
        <span className="muted">
          {detail.family_title ? `${detail.family_title} · ` : ""}
          {classLabel(detail.material_class)}
          {detail.total > 1 ? ` · ${detail.position + 1} of ${detail.total}` : ""}
        </span>
      </header>

      <main className="viewer-body">
        <h1 className="title" style={{ fontSize: 28, marginBottom: 18 }}>
          {unit.label || unit.name}
        </h1>

        {unit.view === "video" ? (
          <Player mediaId={unit.id} maybe={unit.plays_in_browser === "maybe"} />
        ) : unit.view === "document" ? (
          <iframe className="document-frame" src={`/media/${unit.id}/content`} title={unit.name} />
        ) : unit.view === "bundle" ? (
          <section className="surface" style={{ padding: "22px 24px" }}>
            <p style={{ marginTop: 0 }}>
              <strong>An archive, not an episode.</strong> It holds{" "}
              {plural(contained.length || unit.contained_videos, "video")}. Continuum doesn&apos;t
              extract anything into your Vault, and a compressed archive can&apos;t be played from
              inside, so these can&apos;t be watched here yet.
            </p>
            <div className="list" style={{ marginTop: 14 }}>
              {contained.map((video, index) => (
                <div className="list-item" key={`${video.name}-${index}`}>
                  <div>
                    <h3>
                      {video.episode !== null
                        ? `${seasonLabel(video.season)} · episode ${video.episode}`
                        : video.name}
                    </h3>
                    <p className="sub">
                      {video.name} · {formatBytes(video.size_bytes)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : unit.view === "pages" ? (
          <section className="empty">
            <h3>No pages could be read from this archive</h3>
            <p>It is in your Library, but its contents couldn&apos;t be listed.</p>
          </section>
        ) : (
          <section className="empty">
            <h3>Preview isn&apos;t supported for this file yet</h3>
            <p>
              It&apos;s in your Library ({unit.name}, {formatBytes(unit.size_bytes)}), but Continuum
              can&apos;t display this kind of file in the browser.
            </p>
          </section>
        )}

        <nav className="viewer-foot" aria-label="Other files of this work">
          {previousHref ? (
            <Link className="button small ghost" href={previousHref}>
              ← Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="muted">{formatBytes(unit.size_bytes)}</span>
          {nextHref ? (
            <Link className="button small ghost" href={nextHref}>
              Next →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      </main>
    </div>
  );
}
