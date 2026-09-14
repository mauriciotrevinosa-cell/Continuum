/**
 * The episode board: where every episode stands, computed by the API from the
 * project's committed documents. Levels, their labels and what each requires
 * come from the project's own manifest; nothing here knows any project.
 */
import Link from "next/link";
import type { EpisodeLevel, EpisodeStanding, ProjectDetail, ProjectSource } from "@/lib/api";
import { timeAgo } from "@/lib/acquisition";
import { LifecycleChip } from "./project";

const CATEGORY_LABELS: Record<string, string> = {
  structure: "Structure",
  "green-light": "GREEN LIGHT",
  "voice-check-iteration": "Voice check iteration",
  draft: "Draft",
  "panel-script": "Manga panel script",
  "editorial-overview": "Editorial overview",
  addendum: "Addendum",
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category.replace(/-/g, " ");
}

function levelTone(level: string | null, levels: EpisodeLevel[]): string {
  if (level === null) return "muted";
  const index = levels.findIndex((l) => l.id === level);
  return index === 0 ? "ok" : index === 1 ? "accent" : "info";
}

/** Where the project was read from: for Git, the ref and the commit. */
export function SourceLine({ source }: { source: ProjectSource }) {
  if (source.kind !== "git") {
    return <span className="muted">Read from a project folder</span>;
  }
  return (
    <span className="muted" title={source.subject ?? undefined}>
      Git <code>{source.ref}</code> @ <code>{source.commit?.slice(0, 7)}</code>
      {source.committed_at ? ` · committed ${timeAgo(source.committed_at)}` : ""}
    </span>
  );
}

function EpisodeRow({
  projectId,
  episode,
  levels,
}: {
  projectId: string;
  episode: EpisodeStanding;
  levels: EpisodeLevel[];
}) {
  const href = (id: string) =>
    `/projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(id)}`;
  const main = episode.documents.filter((d) => d.category !== "voice-check-iteration");
  const iterations = episode.documents.filter((d) => d.category === "voice-check-iteration");
  return (
    <div className="episode board-row">
      <div className="board-code">
        <span className="episode-code">{episode.code}</span>
        {episode.pages ? <span className="muted tabular">{episode.pages} pp.</span> : null}
      </div>
      <div className="board-body">
        <div className="board-head">
          <h3>{episode.title ?? <span className="muted">Untitled in its documents</span>}</h3>
          <span className={`chip ${levelTone(episode.level, levels)}`}>{episode.label}</span>
        </div>
        <div className="board-docs">
          {main.map((d) => (
            <Link key={d.id} href={href(d.id)} className="board-doc">
              <span className="board-doc-kind">{categoryLabel(d.category)}</span>
              <LifecycleChip lifecycle={d.lifecycle} />
            </Link>
          ))}
          {iterations.length ? (
            <details className="board-iterations">
              <summary>
                {iterations.length} voice-check iteration{iterations.length === 1 ? "" : "s"}
              </summary>
              {iterations.map((d) => (
                <Link key={d.id} href={href(d.id)} className="board-doc">
                  <span className="board-doc-kind">{d.title}</span>
                  {d.resolved_by ? (
                    <span className="chip plain muted">Resolved at GREEN LIGHT</span>
                  ) : (
                    <LifecycleChip lifecycle={d.lifecycle} />
                  )}
                </Link>
              ))}
            </details>
          ) : null}
        </div>
        <p className="sub board-meta">
          {episode.missing.length
            ? `Next level needs: ${episode.missing.map(categoryLabel).join(", ")}`
            : "Nothing missing for its level"}
          {episode.last_commit ? ` · last change ${episode.last_commit}` : ""}
          {episode.last_changed_at ? ` (${timeAgo(episode.last_changed_at)})` : ""}
        </p>
      </div>
    </div>
  );
}

export function EpisodeBoard({ detail }: { detail: ProjectDetail }) {
  const { episodes, levels, episode_summary: summary, project } = detail;
  if (!episodes.length) return null;
  const top = levels[0];
  return (
    <section className="block" aria-labelledby="episode-board">
      <div className="block-head">
        <h2 id="episode-board">
          Episodes
          <small>
            {top ? `${summary.by_level[top.id] ?? 0} of ${summary.episodes} at ${top.label}` : `${summary.episodes}`}
            {summary.pages ? ` · ${summary.pages} provisional pages` : ""}
          </small>
        </h2>
      </div>
      <div className="board-legend">
        {levels.map((level) => (
          <span key={level.id} className={`chip plain ${levelTone(level.id, levels)}`}>
            {level.label}: {summary.by_level[level.id] ?? 0}
          </span>
        ))}
        {summary.unmet ? <span className="chip plain muted">No level yet: {summary.unmet}</span> : null}
      </div>
      <div className="episodes">
        {episodes.map((episode) => (
          <EpisodeRow key={episode.code} projectId={project.id} episode={episode} levels={levels} />
        ))}
      </div>
    </section>
  );
}
