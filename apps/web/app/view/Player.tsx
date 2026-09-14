"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { type Candidate, vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "../library/_vault/useAction";

/**
 * The browser's own video player, fed by byte ranges so seeking works.
 *
 * Whether a given file plays depends on its container and codecs, which the
 * browser alone decides. Instead of guessing, the player tries - and says so
 * plainly when the browser can't.
 *
 * A frame can be captured into the Reference Inbox. The browser draws the
 * paused frame; the server records which held video and which instant it came
 * from. The video itself is never copied.
 */
export function Player({ mediaId, maybe }: { mediaId: string; maybe: boolean }) {
  const [failed, setFailed] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const { busy, error, run } = useAction();
  const [captured, setCaptured] = useState<Candidate[]>([]);

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
          query: { media_id: mediaId, time_ms: Math.round(element.currentTime * 1000) },
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
          browser. It plays in a desktop player such as VLC or mpv.
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
        src={`/media/${mediaId}/content`}
        onError={() => setFailed(true)}
        onLoadedMetadata={(event) => {
          // A reference's "open the captured moment" link lands here as #t<seconds>.
          const match = /^#t(\d+)$/.exec(window.location.hash);
          if (match) event.currentTarget.currentTime = Number(match[1]);
        }}
      />
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
