"use client";

import Link from "next/link";
import { useState } from "react";
import type { Region } from "@/lib/regions";
import { type CharacterSummary, type ReferenceView, type VisualMode, vaultFetch } from "@/lib/vault";
import { Feedback, useAction } from "./useAction";
import { type ProjectChoice, type SpecBody, SpecForm } from "./SpecForm";

export type { ProjectChoice };

function validateReaderReference(spec: SpecBody): void {
  if (!spec.characters.length && !spec.techniques.length && !spec.panel_sources.length) {
    throw new Error("Choose a character, style technique, or scene target before adding this reference.");
  }
}

/**
 * Add the page on screen - or a region drawn on it - to the Character Vault,
 * the Style Vault or a project's scene sources. Nothing is copied: the server
 * records the archive's content hash, the page's entry name and the region.
 */
export function AddReference({
  mediaId,
  page,
  region,
  onClearRegion,
  characters,
  modes,
  projects,
  sourceTitle,
}: {
  mediaId: string;
  page: number;
  region: Region | null;
  onClearRegion: () => void;
  characters: CharacterSummary[];
  modes: VisualMode[];
  projects: ProjectChoice[];
  sourceTitle?: string;
}) {
  const { busy, error, run } = useAction();
  const [added, setAdded] = useState<ReferenceView[]>([]);

  return (
    <aside className="reader-picker surface" aria-label="Add reference">
      <div className="spread">
        <h2 style={{ margin: 0, fontSize: 17 }}>Add reference</h2>
        <span className="muted tabular">Page {page + 1}</span>
      </div>
      <p className="hint">
        {region
          ? `Region ${Math.round(region.width * 100)}% × ${Math.round(region.height * 100)}% of the page.`
          : "Drag on the page to select a face, an outfit, a pose, a panel - or keep the whole page."}
      </p>
      {region ? (
        <button className="button small ghost" type="button" onClick={onClearRegion}>
          Use the whole page instead
        </button>
      ) : null}

      <SpecForm
        characters={characters}
        modes={modes}
        projects={projects}
        busy={busy}
        page={page}
        sourceTitle={sourceTitle}
        submitLabel={region ? "Add this region" : "Add this page"}
        onSubmit={(spec) =>
          run(async () => {
            validateReaderReference(spec);
            const reference = await vaultFetch<ReferenceView>("library/references/from-source", {
              json: { media_id: mediaId, page_index: page, spec: { ...spec, region } },
            });
            setAdded((previous) => [reference, ...previous].slice(0, 5));
            onClearRegion();
            return reference;
          })
        }
      />
      <Feedback error={error} done={null} />

      {added.length ? (
        <div className="stack">
          <span className="eyebrow" style={{ margin: 0 }}>
            Added
          </span>
          {added.map((reference) => (
            <Link key={reference.id} className="list-item" href={`/library/references/${reference.id}`} target="_blank">
              <span>
                {reference.characters[0]
                  ? `${reference.characters[0].character_name} · ${reference.characters
                      .map((link) => link.aspect.toLowerCase().replace(/_/g, " "))
                      .join(" + ")}`
                  : reference.techniques[0]
                    ? reference.techniques[0].facet.toLowerCase().replace(/_/g, " ")
                    : reference.panel_sources[0]
                      ? `Scene source · p${reference.panel_sources[0].page}`
                      : reference.reference_class.toLowerCase()}
              </span>
              <span className="muted">Open ↗</span>
            </Link>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
