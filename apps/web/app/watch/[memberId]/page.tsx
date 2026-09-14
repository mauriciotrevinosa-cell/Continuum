import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiUnreachableError } from "@/lib/api";
import { CatalogNotFound, type MemberState, UUID, catalog } from "@/lib/catalog";
import { MemberWatch } from "./MemberWatch";

export const dynamic = "force-dynamic";

/** Watch one episode stored inside an archive, by member id only. */
export default async function WatchPage({ params }: { params: Promise<{ memberId: string }> }) {
  const { memberId } = await params;
  if (!UUID.test(memberId)) notFound();
  let state: MemberState | null = null;
  let error: string | null = null;
  try {
    state = await catalog.member(memberId);
  } catch (cause) {
    if (cause instanceof CatalogNotFound) notFound();
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  if (!state) {
    return (
      <div className="viewer-message">
        <div className="empty" role="alert">
          <h3>The catalog isn&apos;t reachable</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }
  const unit = state.unit;
  const back = unit?.series_key ? `/library/vault/series/${unit.series_key}` : "/library/vault";
  return (
    <div className="viewer-page">
      <header className="viewer-bar">
        <Link href={back} className="crumb" style={{ margin: 0 }}>
          ← {unit?.series_title ?? "Series"}
        </Link>
        <span className="muted">{state.archive}</span>
      </header>
      <main className="viewer-body">
        <h1 className="title" style={{ fontSize: 28, marginBottom: 6 }}>
          {unit?.label ?? state.name}
        </h1>
        <p className="muted" style={{ marginTop: 0 }}>
          {state.name}
          {unit && unit.confidence !== "HIGH" ? ` · identification ${unit.confidence.toLowerCase()}: ${unit.flags.join("; ")}` : ""}
        </p>
        <MemberWatch initial={state} />
      </main>
    </div>
  );
}
