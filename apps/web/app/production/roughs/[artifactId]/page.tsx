import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { type Readiness, type RoughArtifact, VaultNotFound, vault, words } from "@/lib/vault";
import { ApiDown } from "../../../library/acquisition/_components/ui";
import { PURPOSE_LABELS, ReadinessBanner, TestOnlyChip } from "../../_parts/status";
import { AttemptBuilder } from "./AttemptBuilder";
import { AttemptHistory } from "./AttemptHistory";

export const dynamic = "force-dynamic";

/**
 * The rough workspace for one page or panel: its scene sources and modes,
 * its attempt history with review, and the recipe builder for the next one.
 */
export default async function RoughWorkspacePage({ params }: { params: Promise<{ artifactId: string }> }) {
  const { artifactId } = await params;
  if (!/^[0-9a-f-]{36}$/.test(artifactId)) notFound();
  let artifact: RoughArtifact | null = null;
  let readiness: Readiness | null = null;
  let error: string | null = null;
  try {
    [artifact, readiness] = await Promise.all([vault.artifact(artifactId), vault.readiness()]);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!artifact) return <ApiDown service="production" message={error ?? "no response"} />;
  const [characters, styles] = await Promise.all([
    vault.characters().catch(() => []),
    vault.styles().catch(() => null),
  ]);

  return (
    <>
      <Link className="crumb" href={`/projects/${artifact.project_key}/roughs`}>
        ← Roughs
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">
            Advanced / override workspace · {artifact.project_key} · {artifact.episode}
            {artifact.chapter ? ` · chapter ${artifact.chapter}` : ""} · {PURPOSE_LABELS[artifact.purpose] ?? artifact.purpose}
          </p>
          <h1 className="title">
            Page {artifact.page}
            {artifact.panel ? `, panel ${artifact.panel}` : ""}
          </h1>
          <p className="row" style={{ gap: 8, margin: "4px 0" }}>
            <TestOnlyChip purpose={artifact.purpose} />
          </p>
          <p className="lead">
            {artifact.title || words(artifact.kind)}
            {artifact.panel_script.document
              ? ` · from ${artifact.panel_script.document} v${artifact.panel_script.version ?? "?"}`
              : " · no panel script recorded"}
          </p>
        </div>
      </header>
      <ReadinessBanner readiness={readiness} />

      <section aria-label="Attempts">
        <div className="block-head">
          <h2>
            Attempts <small>{artifact.attempts.length}</small>
          </h2>
        </div>
        <AttemptHistory artifact={artifact} characters={characters} />
      </section>

      <section className="block" aria-label="Next attempt">
        <div className="block-head">
          <h2>Next attempt</h2>
        </div>
        <AttemptBuilder artifact={artifact} characters={characters} modes={styles?.modes ?? []} />
      </section>
    </>
  );
}
