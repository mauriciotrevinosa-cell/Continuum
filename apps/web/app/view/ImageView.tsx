"use client";

import { useState } from "react";
import type { Region } from "@/lib/regions";
import type { CharacterSummary, VisualMode } from "@/lib/vault";
import { AddReference, type ProjectChoice } from "../library/_vault/AddReference";
import { RegionSelector } from "../library/_vault/RegionSelector";

/** A standalone held image, with the same "Add reference" as a manga page. */
export function ImageView({
  mediaId,
  name,
  characters,
  modes,
  projects,
}: {
  mediaId: string;
  name: string;
  characters: CharacterSummary[];
  modes: VisualMode[];
  projects: ProjectChoice[];
}) {
  const [picking, setPicking] = useState(false);
  const [region, setRegion] = useState<Region | null>(null);
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div className="empty" role="alert">
        <h3>This image couldn&apos;t be shown</h3>
        <p>It may be damaged or in a format the browser can&apos;t display.</p>
      </div>
    );
  }
  return (
    <div className="stack" style={picking ? { paddingRight: 400 } : undefined}>
      <div className="row">
        <button
          className={`button small${picking ? " primary" : ""}`}
          type="button"
          aria-pressed={picking}
          onClick={() => {
            setPicking(!picking);
            setRegion(null);
          }}
        >
          {picking ? "Done adding" : "Add reference"}
        </button>
      </div>
      <RegionSelector
        src={`/media/${mediaId}/content`}
        alt={name}
        selecting={picking}
        draft={region}
        onSelect={setRegion}
        onError={() => setFailed(true)}
      />
      {picking ? (
        <AddReference
          mediaId={mediaId}
          page={0}
          region={region}
          onClearRegion={() => setRegion(null)}
          characters={characters}
          modes={modes}
          projects={projects}
        />
      ) : null}
    </div>
  );
}
