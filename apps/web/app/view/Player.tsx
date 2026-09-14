"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { type Candidate, vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../library/_vault/useAction";

/** What the player plays: a held video by media id, or a prepared archive member. */
export type PlayerSource = { kind: "media"; mediaId: string } | { kind: "member"; memberId: string };

/** How often the playback position is saved while a video plays. */
const SAVE_EVERY_MS = 10_000;

/**
 * The browser's own video player, fed by byte ranges so seeking works.
 *
 * Whether a given file plays depends on its container and codecs, which the
 * browser alone decides. Instead of guessing, the player tries - and says so
 * plainly when the browser can't.
 *
 * The playback position is saved while watching and restored next time,
 * unless a link names a moment (#t<seconds>). A frame can be captured into the
 * Reference Inbox: the browser draws the paused frame; the server records
 * which video (or which archived episode) and which instant it came from.
 */
export function Player({ source, maybe }: { source: PlayerSource; maybe: boolean }) {
  const [failed, setFailed] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const lastSaved = useRef(0);
  const { busy, error, run } = useAction();
  const [captured, setCaptured] = useState<Candidate[]>([]);
  const [resumedAt, setResumedAt] = useState<number | null>(null);

  const identity =
    source.kind === "media" ? { media_id: source.mediaId } : { member_id: source.memberId };
  const src =
    source.kind === "media" ? `/media/${source.mediaId}/content` : `/media/member/${source.memberId}/content`;

  const save = useCallback(
    (ended = false) => {
      const element = video.current;
      if (!element || !Number.isFinite(element.currentTime)) return;
      lastSaved.current = Date.now();
      void vaultFetch("catalog/progress/watching", {
        json: {
          ...identity,
          position_ms: Math.round(element.currentTime * 1000),
          duration_ms: Number.isFinite(element.duration) ? Math.round(element.duration * 1000) : null,
          ended,
        },
      }).catch(() => undefined);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- identity is derived from source
    [source.kind === "media" ? source.mediaId : source.memberId],
  );

  useEffect(() => {
    const onHide = () => save();
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, [save]);

  const capture = () =>
    run(async () => {
      const element = video.current;
      if (!element || !element.videoWidth) throw new Error("Play the video to the moment first.");
      element.pause();
      const canvas = document.createElement("canvas");
      canvas.width = element.videoWidth;
      canvas.height = element.videoHeight;
      canvas.getContext("2d")?.drawImage(element, 0, 0);
      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("The frame could not be captured.");
      const result = await vaultFetch<{ candidate: Candidate | null; duplicate_of: Candidate | null }>(
        "library/inbox/frames",
        {
          body: blob,
          query: { ...identity, time_ms: Math.round(element.currentTime * 1000) },
        },
      );
      const candidate = result.candidate ?? result.duplicate_of;
      if (candidate) setCaptured((previous) => [candidate, ...previous].slice(0, 6));
      return result;
    });

  if (failed) {
    return (
      <div className="empty" role="alert">
        <h3>This browser can&apos;t play this file</h3>
        <p>
          The file is in your Library, but its format or codecs aren&apos;t supported by this
          browser (HEVC / x265 in Matroska often isn&apos;t). It plays in a desktop player such as
          VLC or mpv. Its catalog entry, progress and provenance still work.
        </p>
      </div>
    );
  }
  return (
    <div className="player">
      <video
        ref={video}
        controls
        preload="metadata"
        src={src}
        onError={() => setFailed(true)}
        onLoadedMetadata={(event) => {
          const element = event.currentTarget;
          // A reference's "open the captured moment" link lands here as #t<seconds>.
          const match = /^#t(\d+)$/.exec(window.location.hash);
          if (match) {
            element.currentTime = Number(match[1]);
            return;
          }
          void vaultFetch<{ position: { position_ms: number | null; completed_at: string | null } | null }>(
            "catalog/progress/position",
            { query: identity },
          )
            .then(({ position }) => {
              if (position?.position_ms && !position.completed_at) {
                element.currentTime = position.position_ms / 1000;
                setResumedAt(position.position_ms);
              }
            })
            .catch(() => undefined);
        }}
        onTimeUpdate={() => {
          if (Date.now() - lastSaved.current > SAVE_EVERY_MS) save();
        }}
        onPause={() => save()}
        onEnded={() => save(true)}
      />
      {resumedAt ? (
        <p className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
          Resumed where you left off.
        </p>
      ) : null}
      {maybe ? (
        <p className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
          This container plays when the browser supports the codecs inside it.
        </p>
      ) : null}
      <div className="row" style={{ marginTop: 12 }}>
        <button className="button small" type="button" onClick={capture} disabled={busy}>
          {busy ? "Capturing…" : "Capture frame to inbox"}
        </button>
        {captured.length ? (
          <span className="muted">
            Captured at {captured.map((c) => c.display_name.split(" @ ").pop()).join(", ")} ·{" "}
            <Link href="/library/inbox?kind=SCREENSHOT">review in the inbox</Link>
          </span>
        ) : null}
      </div>
      <Feedback error={error} done={null} />
    </div>
  );
}
