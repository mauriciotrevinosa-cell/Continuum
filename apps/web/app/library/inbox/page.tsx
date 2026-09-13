import Link from "next/link";
import { ApiUnreachableError } from "@/lib/api";
import { INTAKE_KINDS, type InboxView, vault, words } from "@/lib/vault";
import { ApiDown, PageHead } from "../acquisition/_components/ui";
import { InboxBoard } from "./InboxBoard";

export const dynamic = "force-dynamic";

const STATUSES = ["INBOX", "ACCEPTED", "DISMISSED"] as const;

/**
 * The Reference Inbox: links, fan art, clips and screenshots arrive here in
 * batches and are classified later - into character, style, monster or scene
 * references - or dismissed.
 */
export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; kind?: string }>;
}) {
  const params = await searchParams;
  const status = STATUSES.includes(params.status as (typeof STATUSES)[number]) ? params.status! : "INBOX";
  const kind = INTAKE_KINDS.includes(params.kind as (typeof INTAKE_KINDS)[number]) ? params.kind : undefined;
  let view: InboxView | null = null;
  let error: string | null = null;
  try {
    view = await vault.inbox(status, kind);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }
  const href = (s: string, k?: string) =>
    `/library/inbox?status=${s}${k ? `&kind=${k}` : ""}`;

  return (
    <>
      <PageHead
        eyebrow="Reference vault"
        title="Inbox"
        lead="Bring in a lot at once and sort it later. Links are only remembered; files stay in Continuum's own library folder; clips become references through the frames you capture."
      />
      {error ? <ApiDown service="reference vault" message={error} /> : null}
      <div className="toolbar">
        <nav className="segmented" aria-label="Status">
          {STATUSES.map((s) => (
            <Link key={s} href={href(s, kind)} data-active={status === s}>
              {words(s)}
            </Link>
          ))}
        </nav>
        <nav className="segmented" aria-label="Kind">
          <Link href={href(status)} data-active={!kind}>
            All
          </Link>
          {INTAKE_KINDS.map((k) => (
            <Link key={k} href={href(status, k)} data-active={kind === k}>
              {words(k)}
            </Link>
          ))}
        </nav>
      </div>
      {view ? <InboxBoard view={view} status={status} /> : null}
    </>
  );
}
