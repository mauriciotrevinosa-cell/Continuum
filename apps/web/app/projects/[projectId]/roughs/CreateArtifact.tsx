"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { type RoughArtifact, type RoughPurpose, vaultFetch } from "@/lib/vault";
import { Select } from "../../../library/_vault/SpecForm";
import { Feedback, useAction } from "../../../library/_vault/useAction";

/** Open the manual rough workspace for one page or panel of the project. */
export function CreateArtifact({
  projectId,
  scripts,
  defaultPurpose,
}: {
  projectId: string;
  scripts: { id: string; episode: string; label: string }[];
  defaultPurpose: RoughPurpose;
}) {
  const router = useRouter();
  const { busy, error, run } = useAction();
  const [episode, setEpisode] = useState(scripts[0]?.episode || "S1E1");
  const [purpose, setPurpose] = useState<RoughPurpose>(defaultPurpose);
  const [chapter, setChapter] = useState("1");
  const [page, setPage] = useState("");
  const [panel, setPanel] = useState("");
  const [title, setTitle] = useState("");
  const [script, setScript] = useState(scripts[0]?.id ?? "");
  const [brief, setBrief] = useState("");
  return (
    <form
      className="surface panel stack"
      onSubmit={async (event) => {
        event.preventDefault();
        const artifact = await run(() =>
          vaultFetch<RoughArtifact>(`projects/${projectId}/rough-artifacts`, {
            json: {
              episode,
              chapter: chapter ? Number(chapter) : null,
              page: Number(page),
              panel: panel ? Number(panel) : null,
              title,
              brief,
              panel_script_document: script || null,
              purpose,
            },
          }),
        );
        if (artifact) router.push(`/production/roughs/${artifact.id}`);
      }}
    >
      <h3>Rough a page or panel by hand</h3>
      <div className="form-row" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
        <div className="field compact">
          <label>
            Episode
            <input value={episode} onChange={(e) => setEpisode(e.target.value)} required style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Chapter
            <input type="number" min={1} value={chapter} onChange={(e) => setChapter(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Page
            <input type="number" min={1} value={page} onChange={(e) => setPage(e.target.value)} required style={{ width: "100%" }} />
          </label>
        </div>
        <div className="field compact">
          <label>
            Panel (empty for the whole page)
            <input type="number" min={1} value={panel} onChange={(e) => setPanel(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
      </div>
      <div className="form-row" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <div className="field compact">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <Select
          label="Panel script (version comes from the committed document)"
          value={script}
          onChange={(value) => {
            setScript(value);
            const chosen = scripts.find((s) => s.id === value);
            if (chosen?.episode) setEpisode(chosen.episode);
          }}
          options={scripts.map((s) => ({ value: s.id, label: s.label }))}
          empty="No script"
        />
      </div>
      <Select
        label="Purpose"
        value={purpose}
        onChange={(value) => setPurpose(value as RoughPurpose)}
        options={[
          { value: "WORKFLOW_TEST", label: "Workflow test - non-canon, never counted, never creatively approved" },
          { value: "NON_CANON_SAMPLE", label: "Non-canon sample - quality validation, never project artwork" },
          { value: "PRODUCTION", label: "Production page or panel - counts toward the manga once creatively approved" },
        ]}
      />
      <div className="field">
        <label>
          Brief
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="What the panel script asks this page/panel to do." style={{ width: "100%" }} />
        </label>
      </div>
      <div className="row">
        <button className="button primary small" type="submit" disabled={busy || !page}>
          Open rough workspace
        </button>
        <Feedback error={error} done={null} />
      </div>
    </form>
  );
}
