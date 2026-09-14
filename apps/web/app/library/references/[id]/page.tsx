import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError, projects as projectsApi } from "@/lib/api";
import { type ReferenceView, VaultNotFound, referenceImage, vault, words } from "@/lib/vault";
import { ApiDown } from "../../acquisition/_components/ui";
import { OriginChip, SourceLink, referenceTitle } from "../../_vault/parts";
import { ReferenceEditor } from "./ReferenceEditor";

export const dynamic = "force-dynamic";

function Provenance({ reference }: { reference: ReferenceView }) {
  const p = reference.provenance ?? {};
  const kind = String(p.kind ?? "");
  const lines: [string, React.ReactNode][] = [];
  if (kind === "source_locator") lines.push(["Added from", "a held file, by content hash"]);
  if (kind === "source_frame") lines.push(["Captured from", "a held video, at a recorded instant"]);
  if (kind === "user_assertion") lines.push(["Added by", "you (upload)"]);
  if (kind === "inbox") lines.push(["Accepted from", `the inbox (${words(String(p.intake_kind ?? ""))})`]);
  if (kind === "rough_attempt") lines.push(["Approved from", `rough attempt ${String(p.attempt ?? "")}`]);
  if (typeof p.video_locator === "string") lines.push(["Video", <code key="v">{p.video_locator}</code>]);
  return (
    <dl className="kv">
      {lines.map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
      <dt>Locator</dt>
      <dd>
        <code>{reference.locator}</code>
      </dd>
      {reference.region ? (
        <>
          <dt>Region</dt>
          <dd className="tabular">
            x {reference.region.x} · y {reference.region.y} · {reference.region.width} ×{" "}
            {reference.region.height}
          </dd>
        </>
      ) : null}
      {reference.source_url ? (
        <>
          <dt>Link</dt>
          <dd>
            <a href={reference.source_url} target="_blank" rel="noopener noreferrer nofollow">
              {reference.source_url}
            </a>
          </dd>
        </>
      ) : null}
      {reference.creator_handle ? (
        <>
          <dt>Creator</dt>
          <dd>{reference.creator_handle}</dd>
        </>
      ) : null}
      <dt>Added</dt>
      <dd>{reference.created_at ? new Date(reference.created_at).toLocaleString() : "—"}</dd>
    </dl>
  );
}

export default async function ReferencePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/.test(id)) notFound();
  let reference: ReferenceView | null = null;
  let error: string | null = null;
  try {
    reference = await vault.reference(id);
  } catch (cause) {
    if (cause instanceof VaultNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!reference) {
    return <ApiDown service="reference vault" message={error ?? "no response"} />;
  }
  const [characters, styles, projects] = await Promise.all([
    vault.characters().catch(() => []),
    vault.styles().catch(() => null),
    projectsApi.list().catch(() => []),
  ]);

  return (
    <>
      <Link className="crumb" href="/library/references">
        ← References
      </Link>
      <header className="page-head">
        <div>
          <p className="eyebrow">
            {words(reference.reference_class)} reference
          </p>
          <h1 className="title" style={{ fontSize: 32 }}>
            {referenceTitle(reference)}
          </h1>
          <div className="row" style={{ marginTop: 12 }}>
            <OriginChip origin={reference.origin} />
            {reference.uses.map((use) => (
              <span className="chip quiet" key={use}>
                {words(use)}
              </span>
            ))}
          </div>
        </div>
        <SourceLink reference={reference} />
      </header>

      <div className="two-col">
        <div className="stack">
          <div className="surface panel output-view">
            {reference.previewable ? (
              // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
              <img src={referenceImage(reference.id, true)} alt={referenceTitle(reference)} style={{ background: "transparent" }} />
            ) : (
              <p className="muted">PDF pages open in the viewer.</p>
            )}
            {reference.region && reference.previewable ? (
              <p className="hint" style={{ marginTop: 10 }}>
                Showing the selected region.{" "}
                <a href={referenceImage(reference.id, false)} target="_blank" rel="noreferrer">
                  See the whole unit ↗
                </a>
              </p>
            ) : null}
          </div>
          <div className="surface">
            <Provenance reference={reference} />
          </div>
        </div>
        <ReferenceEditor
          reference={reference}
          characters={characters}
          modes={styles?.modes ?? []}
          projects={projects.map((p) => ({ id: p.id, title: p.title }))}
        />
      </div>
    </>
  );
}
