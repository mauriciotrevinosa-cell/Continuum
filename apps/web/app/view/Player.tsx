"use client";

import { useState } from "react";

/**
 * The browser's own video player, fed by byte ranges so seeking works.
 *
 * Whether a given file plays depends on its container and codecs, which the
 * browser alone decides. Instead of guessing, the player tries - and says so
 * plainly when the browser can't.
 */
export function Player({ mediaId, maybe }: { mediaId: string; maybe: boolean }) {
  const [failed, setFailed] = useState(false);
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
        controls
        preload="metadata"
        src={`/media/${mediaId}/content`}
        onError={() => setFailed(true)}
      />
      {maybe ? (
        <p className="muted" style={{ marginTop: 10, fontSize: 12.5 }}>
          This container plays when the browser supports the codecs inside it.
        </p>
      ) : null}
    </div>
  );
}
