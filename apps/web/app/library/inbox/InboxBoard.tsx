"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  type Candidate,
  REFERENCE_CLASSES,
  REFERENCE_USES,
  USER_ORIGINS,
  type InboxView,
  VaultActionError,
  vaultFetch,
  words,
} from "@/lib/vault";
import { describeTally, type IntakeTally, intakeHint } from "@/lib/intake";
import { parseLinks } from "@/lib/links";
import { OriginChip } from "../_vault/parts";
import { Select, Toggles } from "../_vault/SpecForm";
import { Feedback, useAction } from "../_vault/useAction";

const content = (id: string) => `/vault-api/library/inbox/candidates/${id}/content`;

function Defaults({
  origin,
  setOrigin,
  suggested,
  setSuggested,
  uses,
  setUses,
  tags,
  setTags,
}: {
  origin: string;
  setOrigin: (v: string) => void;
  suggested: string;
  setSuggested: (v: string) => void;
  uses: string[];
  setUses: (v: string[]) => void;
  tags: string;
  setTags: (v: string) => void;
}) {
  return (
    <div className="stack">
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
        <Select label="Origin for this batch" value={origin} onChange={setOrigin} options={USER_ORIGINS} />
        <Select label="Suggested class" value={suggested} onChange={setSuggested} options={REFERENCE_CLASSES} empty="Decide later" />
        <div className="field compact">
          <label>
            Tags for the batch
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="winter, coat" style={{ width: "100%" }} />
          </label>
        </div>
      </div>
      <div className="field">
        <span className="label">Intended uses</span>
        <Toggles values={REFERENCE_USES} selected={uses} onChange={setUses} label="Intended uses" />
      </div>
    </div>
  );
}

function ClipFrame({ candidate }: { candidate: Candidate }) {
  const video = useRef<HTMLVideoElement>(null);
  const { busy, error, run } = useAction();
  return (
    <div className="stack">
      <video ref={video} src={content(candidate.id)} controls preload="metadata" style={{ width: "100%", borderRadius: 9 }} />
      <button
        className="button small"
        type="button"
        disabled={busy}
        onClick={() =>
          run(async () => {
            const element = video.current;
            if (!element || !element.videoWidth) throw new Error("Play the clip to the moment first.");
            element.pause();
            const canvas = document.createElement("canvas");
            canvas.width = element.videoWidth;
            canvas.height = element.videoHeight;
            canvas.getContext("2d")?.drawImage(element, 0, 0);
            const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/png"));
            if (!blob) throw new Error("The frame could not be captured.");
            return vaultFetch(`library/inbox/candidates/${candidate.id}/clip-frame`, {
              body: blob,
              query: { time_ms: Math.round(element.currentTime * 1000) },
            });
          }, "Frame captured.")
        }
      >
        Capture this frame
      </button>
      <Feedback error={error} done={null} />
    </div>
  );
}

function CandidateCard({
  candidate,
  selected,
  onToggle,
  fallbackClass,
}: {
  candidate: Candidate;
  selected: boolean;
  onToggle: () => void;
  fallbackClass: string;
}) {
  const { busy, error, run } = useAction();
  const attach = useRef<HTMLInputElement>(null);
  const isVideo = candidate.intake_kind === "VIDEO";
  const reference = candidate.reference_id;
  return (
    <div className="ref-card" data-selected={selected}>
      {candidate.status === "INBOX" ? (
        <label className="check" style={{ position: "absolute", top: 12, left: 12, zIndex: 2 }}>
          <input type="checkbox" checked={selected} onChange={onToggle} aria-label="Select" />
        </label>
      ) : null}
      {isVideo && candidate.has_file ? (
        <ClipFrame candidate={candidate} />
      ) : candidate.has_file ? (
        <div className="ref-thumb">
          {/* eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id */}
          <img src={content(candidate.id)} alt={candidate.display_name || "Candidate"} loading="lazy" />
        </div>
      ) : (
        <div className="ref-thumb">
          <span className="muted">A link only - nothing was fetched.</span>
        </div>
      )}
      <span className="ref-label" title={candidate.display_name}>
        {candidate.display_name || words(candidate.intake_kind)}
      </span>
      <span className="ref-meta">
        <OriginChip origin={candidate.origin} tiny />
        <span className="chip muted plain tiny">{words(candidate.intake_kind)}</span>
        {candidate.suggested_class ? <span className="chip quiet tiny">{words(candidate.suggested_class)}</span> : null}
      </span>
      {candidate.source_url ? <span className="candidate-link">{candidate.source_url}</span> : null}
      {candidate.creator_handle ? (
        <span className="hint">
          {candidate.creator_handle}
          {candidate.capture?.creator_handle_source === "filename" ? " · from the file name" : ""}
        </span>
      ) : null}
      {candidate.capture?.original_format ? (
        <span className="hint">
          {String(candidate.capture.original_format)} original kept · working copy PNG
        </span>
      ) : null}
      {candidate.intended_uses.length || candidate.tags.length ? (
        <span className="hint">
          {[...candidate.intended_uses.map(words), ...candidate.tags.map((t) => `#${t}`)].join(" · ")}
        </span>
      ) : null}
      {typeof candidate.capture?.video_locator === "string" ? (
        <span className="hint">Frame of {candidate.capture.kind === "held_video_frame" ? "a held episode" : "a clip"}</span>
      ) : null}

      {candidate.status === "INBOX" ? (
        <div className="row">
          {!candidate.has_file && candidate.intake_kind === "URL" ? (
            <>
              <input
                ref={attach}
                type="file"
                accept="image/*,.heic,.heif"
                hidden
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file)
                    run(() =>
                      vaultFetch(`library/inbox/candidates/${candidate.id}/attach`, {
                        body: file,
                        query: { row_version: candidate.row_version },
                      }),
                    );
                }}
              />
              <button className="button small" type="button" disabled={busy} onClick={() => attach.current?.click()}>
                Attach image
              </button>
            </>
          ) : !isVideo ? (
            <button
              className="button small primary"
              type="button"
              disabled={busy}
              onClick={() =>
                run(() =>
                  vaultFetch(`library/inbox/candidates/${candidate.id}/accept`, {
                    json: {
                      row_version: candidate.row_version,
                      reference_class: candidate.suggested_class ?? fallbackClass,
                    },
                  }),
                )
              }
            >
              Accept
            </button>
          ) : null}
          <button
            className="button small ghost"
            type="button"
            disabled={busy}
            onClick={() =>
              run(() =>
                vaultFetch(`library/inbox/candidates/${candidate.id}/dismiss`, {
                  json: { row_version: candidate.row_version },
                }),
              )
            }
          >
            Dismiss
          </button>
        </div>
      ) : candidate.status === "DISMISSED" ? (
        <button
          className="button small ghost"
          type="button"
          disabled={busy}
          onClick={() =>
            run(() =>
              vaultFetch(`library/inbox/candidates/${candidate.id}/restore`, {
                json: { row_version: candidate.row_version },
              }),
            )
          }
        >
          Restore
        </button>
      ) : reference ? (
        <Link className="button small ghost" href={`/library/references/${reference}`}>
          Open reference →
        </Link>
      ) : null}
      <Feedback error={error} done={null} />
    </div>
  );
}

/**
 * Bring material in without organising it one item at a time: paste links,
 * drop folders of images, clips and screenshots, then triage in bulk.
 */
export function InboxBoard({ view, status }: { view: InboxView; status: string }) {
  const intake = useAction();
  const bulk = useAction();
  const [tab, setTab] = useState<"links" | "files">("files");
  const [origin, setOrigin] = useState("FAN_ART");
  const [suggested, setSuggested] = useState("");
  const [uses, setUses] = useState<string[]>([]);
  const [tags, setTags] = useState("");
  const [handle, setHandle] = useState("");
  const [links, setLinks] = useState("");
  const [screenshots, setScreenshots] = useState(false);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [bulkClass, setBulkClass] = useState("CANON");
  const [bulkUses, setBulkUses] = useState<string[]>([]);
  const [bulkTags, setBulkTags] = useState("");
  const tagList = () => tags.split(",").map((t) => t.trim()).filter(Boolean);

  const upload = (files: File[]) =>
    intake.run(async () => {
      const tally: IntakeTally = { taken: 0, duplicates: [], refused: [], skipped: [] };
      const usable = files.filter((f) => {
        const hint = intakeHint(f.name, f.type, screenshots);
        if (!hint) tally.skipped.push(f.name);
        return hint !== null;
      });
      if (!usable.length) throw new VaultActionError(describeTally(tally), 422);
      const batch = await vaultFetch<{ id: string }>("library/inbox/batches", {
        method: "POST",
        query: { kind: screenshots ? "SCREENSHOT" : "IMAGE", label: `${usable.length} files` },
      });
      for (const [index, file] of usable.entries()) {
        setProgress(`Taking in ${index + 1} of ${usable.length}…`);
        try {
          const result = await vaultFetch<{ duplicate: boolean }>("library/inbox/files", {
            body: file,
            query: {
              kind: intakeHint(file.name, file.type, screenshots) ?? "IMAGE",
              batch_id: batch.id,
              label: file.name,
              origin,
              suggested_class: suggested || undefined,
              uses: uses.join(",") || undefined,
              tags: tagList().join(",") || undefined,
              creator_handle: handle || undefined,
            },
          });
          if (result.duplicate) tally.duplicates.push(file.name);
          else tally.taken += 1;
        } catch (cause) {
          tally.refused.push(`${file.name}: ${cause instanceof Error ? cause.message : String(cause)}`);
        }
      }
      setProgress(null);
      if (tally.refused.length || tally.skipped.length || tally.duplicates.length) {
        throw new VaultActionError(describeTally(tally), 200);
      }
    }, "Taken in.");

  const addLinks = () =>
    intake.run(async () => {
      const entries = parseLinks(links).map((e) => ({
        ...e,
        creator_handle: e.creator_handle ?? (handle || null),
      }));
      if (!entries.length) throw new VaultActionError("Paste at least one http(s) link.", 422);
      const result = await vaultFetch<{ created: unknown[]; skipped: { input: string; reason: string }[] }>(
        "library/inbox/urls",
        {
          json: {
            label: `${entries.length} links`,
            entries,
            defaults: { origin, suggested_class: suggested || null, intended_uses: uses, tags: tagList() },
          },
        },
      );
      setLinks("");
      if (result.skipped.length) {
        throw new VaultActionError(
          `${result.created.length} added; skipped ${result.skipped.map((s) => `${s.input} (${s.reason})`).join(", ")}`,
          200,
        );
      }
    }, "Links added. Nothing was fetched.");

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="stack">
      {status === "INBOX" ? (
        <section className="surface panel stack" aria-label="Bring material in">
          <div className="spread">
            <div className="tabs" role="tablist">
              <button type="button" role="tab" aria-selected={tab === "files"} onClick={() => setTab("files")}>
                Images, clips, screenshots
              </button>
              <button type="button" role="tab" aria-selected={tab === "links"} onClick={() => setTab("links")}>
                Links
              </button>
            </div>
            <div className="field compact" style={{ minWidth: 220 }}>
              <label>
                Creator handle
                <input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@artist" style={{ width: "100%" }} />
              </label>
            </div>
          </div>

          {tab === "files" ? (
            <>
              <label
                className="dropzone"
                data-over={over}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOver(true);
                }}
                onDragLeave={() => setOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setOver(false);
                  upload(Array.from(e.dataTransfer.files));
                }}
              >
                <strong>Drop images, video clips or screenshots</strong>
                <span className="hint">or choose files - they are kept in Continuum&apos;s library folder, never in your Vault</span>
                <input
                  type="file"
                  multiple
                  accept="image/*,.heic,.heif,video/mp4,video/webm,video/quicktime,video/x-matroska"
                  onChange={(e) => upload(Array.from(e.target.files ?? []))}
                />
              </label>
              <label className="check">
                <input type="checkbox" checked={screenshots} onChange={(e) => setScreenshots(e.target.checked)} />
                These images are screenshots
              </label>
            </>
          ) : (
            <div className="field">
              <label>
                One link per line - add @handle and #tags on the same line if you like
                <textarea
                  value={links}
                  onChange={(e) => setLinks(e.target.value)}
                  placeholder={"https://art.example.org/works/123 @artist #winter\nhttps://video.example.org/v/42 #fight"}
                  style={{ width: "100%", minHeight: 120, fontFamily: "var(--mono)", fontSize: 12.5 }}
                />
              </label>
              <p className="hint">Links are stored and shown - never opened, scraped or downloaded. Attach the image you saved to accept one.</p>
              <div>
                <button className="button primary small" type="button" disabled={intake.busy} onClick={addLinks}>
                  Add links
                </button>
              </div>
            </div>
          )}
          <Defaults
            origin={origin}
            setOrigin={setOrigin}
            suggested={suggested}
            setSuggested={setSuggested}
            uses={uses}
            setUses={setUses}
            tags={tags}
            setTags={setTags}
          />
          {progress ? <p className="hint" role="status">{progress}</p> : null}
          <Feedback error={intake.error} done={intake.done} />
        </section>
      ) : null}

      {status === "INBOX" && view.candidates.length ? (
        <section className="surface panel stack" aria-label="Triage selected">
          <div className="spread">
            <strong>{selected.length} selected</strong>
            <span className="row">
              <button className="button small ghost" type="button" onClick={() => setSelected(view.candidates.map((c) => c.id))}>
                Select all
              </button>
              <button className="button small ghost" type="button" onClick={() => setSelected([])}>
                Clear
              </button>
            </span>
          </div>
          <div className="form-row" style={{ gridTemplateColumns: "1fr 2fr", alignItems: "end" }}>
            <Select label="Class when accepting" value={bulkClass} onChange={setBulkClass} options={REFERENCE_CLASSES} />
            <div className="field compact">
              <label>
                Add tags
                <input value={bulkTags} onChange={(e) => setBulkTags(e.target.value)} placeholder="monster, rain" style={{ width: "100%" }} />
              </label>
            </div>
          </div>
          <Toggles values={REFERENCE_USES} selected={bulkUses} onChange={setBulkUses} label="Set intended uses" />
          <div className="row">
            <button
              className="button small"
              type="button"
              disabled={!selected.length || bulk.busy}
              onClick={() =>
                bulk.run(async () => {
                  const changes: Record<string, unknown> = { suggested_class: bulkClass };
                  if (bulkUses.length) changes.intended_uses = bulkUses;
                  const add = bulkTags.split(",").map((t) => t.trim()).filter(Boolean);
                  if (add.length) changes.add_tags = add;
                  await vaultFetch("library/inbox/bulk-update", { json: { ids: selected, changes } });
                }, "Updated.")
              }
            >
              Apply to selected
            </button>
            <button
              className="button small primary"
              type="button"
              disabled={!selected.length || bulk.busy}
              onClick={() =>
                bulk.run(async () => {
                  const result = await vaultFetch<{ accepted: unknown[]; skipped: { id: string; reason: string }[] }>(
                    "library/inbox/bulk-accept",
                    { json: { ids: selected, reference_class: bulkClass, uses: bulkUses.length ? bulkUses : null } },
                  );
                  setSelected([]);
                  if (result.skipped.length) {
                    throw new VaultActionError(
                      `${result.accepted.length} accepted; ${result.skipped.length} skipped: ${[...new Set(result.skipped.map((s) => s.reason))].join("; ")}`,
                      200,
                    );
                  }
                }, "Accepted into the vault.")
              }
            >
              Accept selected
            </button>
          </div>
          <Feedback error={bulk.error} done={bulk.done} />
        </section>
      ) : null}

      {view.candidates.length ? (
        <div className="ref-grid">
          {view.candidates.map((candidate) => (
            <CandidateCard
              key={candidate.id}
              candidate={candidate}
              selected={selected.includes(candidate.id)}
              onToggle={() => toggle(candidate.id)}
              fallbackClass={bulkClass}
            />
          ))}
        </div>
      ) : (
        <div className="empty">
          <h3>{status === "INBOX" ? "The inbox is empty" : `Nothing ${words(status).toLowerCase()}`}</h3>
          <p>{status === "INBOX" ? "Drop files or paste links above." : "Candidates appear here after triage."}</p>
        </div>
      )}
    </div>
  );
}
