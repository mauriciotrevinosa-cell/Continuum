import { ApiUnreachableError } from "@/lib/api";
import { type ExternalResourceListing, vault, words } from "@/lib/vault";
import { ApiDown, Empty, PageHead } from "../acquisition/_components/ui";
import { ImportRegistry, ResourceDecision } from "./ResourceForms";

export const dynamic = "force-dynamic";

const ACCESS_TONE: Record<string, string> = {
  OPEN: "ok",
  GRANTED: "ok",
  REQUESTED: "info",
  NOT_REQUESTED: "muted",
  DENIED: "err",
  UNKNOWN: "warn",
};

/**
 * Datasets, annotation sets, models and tools Continuum may use. The committed
 * registry proposes what each is good for; a person decides access, license
 * acceptance and what material from it may be used for. Nothing here downloads
 * anything, and no import ever approves training.
 */
export default async function DatasetsPage() {
  let listing: ExternalResourceListing | null = null;
  let error: string | null = null;
  try {
    listing = await vault.externalResources();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!listing) return <ApiDown service="the library" message={error ?? "no response"} />;
  const { resources, intake_roots, uses, access_states } = listing;

  return (
    <>
      <PageHead
        eyebrow="Visual Knowledge"
        title="Datasets & tools"
        lead="What each resource is, its license, whether access was requested or granted, and what material from it may be used for. Retrieval, validation and training are separate decisions; an import never grants training."
        aside={<ImportRegistry />}
      />
      {resources.length ? (
        <div className="stack" style={{ gap: 12 }}>
          {resources.map((r) => (
            <section key={r.key} className="surface panel stack" aria-label={r.key}>
              <div className="spread">
                <b className="mono">{r.key}</b>
                <span className="row" style={{ gap: 6 }}>
                  <span className="chip tiny quiet">{words(r.kind)}</span>
                  <span className={`chip tiny ${ACCESS_TONE[r.access_state] ?? "muted"}`}>
                    {words(r.access_state)}
                  </span>
                  {r.registry.priority ? <span className="chip tiny quiet">priority {r.registry.priority}</span> : null}
                </span>
              </div>
              <p className="hint" style={{ margin: 0 }}>
                {r.license_summary}
              </p>
              <dl className="kv-inline">
                <dt>Registry proposes</dt>
                <dd>{r.proposed_uses.map(words).join(", ") || "nothing (unverified)"}</dd>
                <dt>Allowed</dt>
                <dd>{r.allowed_uses.map(words).join(", ") || "nothing"}</dd>
                <dt>License accepted</dt>
                <dd>
                  {r.license_accepted_at
                    ? `${r.license_accepted_at.slice(0, 10)} - ${r.license_acceptance_note}`
                    : "not accepted"}
                </dd>
                <dt>Bytes</dt>
                <dd>
                  {r.intake_root_key
                    ? `${r.intake_root_key} · ${r.items} imported reference(s)`
                    : "not bound to an intake folder"}
                </dd>
                <dt>Status</dt>
                <dd>{r.registry.status ? words(r.registry.status) : "-"}</dd>
                {r.urls.length ? (
                  <>
                    <dt>Published</dt>
                    <dd>
                      {r.urls.map((url) => (
                        <a key={url} href={url} target="_blank" rel="noreferrer noopener" style={{ marginRight: 8 }}>
                          {new URL(url).host}
                        </a>
                      ))}
                    </dd>
                  </>
                ) : null}
              </dl>
              <ResourceDecision resource={r} intakeRoots={intake_roots} uses={uses} accessStates={access_states} />
            </section>
          ))}
        </div>
      ) : (
        <Empty title="No resources registered">
          <p>Import the committed registry (docs/creative/visual_knowledge/dataset_registry_v0.1.json).</p>
        </Empty>
      )}
    </>
  );
}
