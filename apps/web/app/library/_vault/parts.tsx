/**
 * Presentational pieces for the reference vault. Server-safe: no hooks.
 *
 * A reference is shown image first, with its origin always visible - fan art
 * never passes as source material, and generated work never as either.
 */
import Link from "next/link";
import {
  ORIGIN_LABEL,
  ORIGIN_TONE,
  type ReferenceView,
  readerHref,
  referenceImage,
  words,
} from "@/lib/vault";

export function OriginChip({ origin, tiny = false }: { origin: string; tiny?: boolean }) {
  return (
    <span className={`chip ${ORIGIN_TONE[origin] ?? "muted"} plain${tiny ? " tiny" : ""}`}>
      {ORIGIN_LABEL[origin] ?? words(origin)}
    </span>
  );
}

export function referenceTitle(reference: ReferenceView): string {
  if (reference.label) return reference.label;
  const held = reference.provenance?.held_name;
  if (typeof held === "string") {
    const page = reference.unit_index !== null ? ` · p${reference.unit_index + 1}` : "";
    return `${held}${page}`;
  }
  return words(reference.reference_class);
}

export function Thumb({ reference, crop = true }: { reference: ReferenceView; crop?: boolean }) {
  return (
    <div className="ref-thumb">
      {reference.previewable ? (
        // eslint-disable-next-line @next/next/no-img-element -- private local bytes served by id
        <img src={referenceImage(reference.id, crop)} alt={referenceTitle(reference)} loading="lazy" />
      ) : (
        <span className="muted">PDF page - open it in the viewer</span>
      )}
    </div>
  );
}

export function RefCard({
  reference,
  href,
  note,
}: {
  reference: ReferenceView;
  href?: string;
  note?: React.ReactNode;
}) {
  const body = (
    <>
      <Thumb reference={reference} />
      {reference.favorite ? (
        <span className="star" aria-label="Favorite">
          ★
        </span>
      ) : null}
      <span className="ref-label" title={referenceTitle(reference)}>
        {referenceTitle(reference)}
      </span>
      <span className="ref-meta">
        <OriginChip origin={reference.origin} tiny />
        <span className="chip muted plain tiny">{words(reference.reference_class)}</span>
        {reference.region ? <span className="chip quiet tiny">Region</span> : null}
      </span>
      {note ? <span className="hint">{note}</span> : null}
    </>
  );
  return href ? (
    <Link className="ref-card" href={href}>
      {body}
    </Link>
  ) : (
    <div className="ref-card">{body}</div>
  );
}

export function SourceLink({ reference }: { reference: ReferenceView }) {
  const href = readerHref(reference.source);
  if (!href) {
    return reference.source && !reference.source.available ? (
      <span className="muted">{reference.source.reason ?? "Not held media"}</span>
    ) : null;
  }
  const where =
    reference.source?.page_index !== null && reference.source?.page_index !== undefined
      ? `page ${reference.source.page_index + 1}`
      : reference.source?.time_ms !== null && reference.source?.time_ms !== undefined
        ? "the captured moment"
        : "the original";
  return (
    <Link className="button small ghost" href={href}>
      Open {where} in the viewer ↗
    </Link>
  );
}
