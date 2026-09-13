import Link from "next/link";
import {
  ApiUnreachableError,
  type FamilyProgress,
  type IntakeUnit,
  type IntakeView,
  type ReviewItem,
  acquisition,
} from "@/lib/api";
import { basename, classLabel, plural } from "@/lib/acquisition";
import { ActionButton } from "../_components/ActionButton";
import { ApiDown, Empty, PageHead } from "../_components/ui";
import { refreshIntakeAction } from "../actions";

export const dynamic = "force-dynamic";

const SECTIONS: { key: IntakeUnit["section"]; title: string; note: string }[] = [
  { key: "identify", title: "Needs identification", note: "Continuum could not tell what these are." },
  { key: "ready", title: "Ready to ingest", note: "Identified, with a place in your Vault." },
  { key: "incomplete", title: "Incomplete downloads", note: "Left alone until they finish." },
  { key: "conflict", title: "Can't be placed", note: "Something in the way needs your decision." },
  { key: "known", title: "Already in your Library", note: "Byte-identical copies of files you have." },
];

function believes(unit: IntakeUnit): string {
  if (unit.family || unit.work) {
    return `Continuum thinks this is ${[unit.work, unit.family].filter(Boolean).join(" in ")}.`;
  }
  if (unit.series.length) return `The files call themselves “${unit.series[0]}”.`;
  return "Nothing in the files names what they are.";
}

function whyUnsure(unit: IntakeUnit): string {
  const reason = unit.action.replace(/^left-in-intake:\s*/i, "");
  if (unit.section === "identify") {
    if (/low-confidence/i.test(reason)) return "The best title match is too weak to trust.";
    if (/no destination/i.test(reason)) return "It matches a work that has no place in the Vault yet.";
    if (/colour/i.test(reason)) return "It looks like a colour edition, which is kept apart on purpose.";
    if (/fan/i.test(reason)) return "It looks like fan material, which is never imported.";
    return "No catalogued title matched.";
  }
  if (unit.section === "ready") return "The title matched a catalogued work exactly.";
  if (unit.section === "known") return "The same bytes are already in your Vault.";
  if (unit.section === "incomplete") return "The download has not finished.";
  return reason;
}

function todo(unit: IntakeUnit): string {
  switch (unit.section) {
    case "identify":
      return "Rename the folder to the work's title, or map it to a work, then re-read intake.";
    case "ready":
      return "Import it with the acquisition tool when you're ready. This screen never imports.";
    case "known":
      return "Nothing to do. Delete the intake copy yourself if you don't need it.";
    case "incomplete":
      return "Let the download finish, then re-read intake.";
    default:
      return "Resolve the conflict, then re-read intake.";
  }
}

function UnitItem({ unit }: { unit: IntakeUnit }) {
  return (
    <div className="list-item intake-item">
      <div style={{ minWidth: 0 }}>
        <h3>{unit.unit}</h3>
        <p>{believes(unit)}</p>
        <p className="muted">
          {whyUnsure(unit)} {plural(unit.files, "file")} · from {unit.source}
          {unit.languages.length ? ` · ${unit.languages.join(", ")}` : ""}
        </p>
        <p className="todo">{todo(unit)}</p>
        {unit.unofficial_provenance.length ? (
          <p className="muted">Downloaded from {unit.unofficial_provenance.join(", ")}.</p>
        ) : null}
      </div>
      <div className="side">
        <code title={unit.path}>{basename(unit.path)}</code>
      </div>
    </div>
  );
}

/**
 * Files that entered Continuum, and help identifying them. Nothing on this
 * screen moves or writes anything in the Vault; importing stays a command.
 */
export default async function IntakePage() {
  let data: IntakeView | null = null;
  let families: FamilyProgress[] = [];
  let error: string | null = null;
  try {
    [data, families] = await Promise.all([acquisition.intake(), acquisition.families()]);
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const units = data?.units ?? [];
  const uncatalogued = families
    .flatMap((f) =>
      f.materials
        .filter((m) => m.unmapped_files > 0)
        .map((m) => ({ family: f, material: m })),
    )
    .sort((a, b) => b.material.unmapped_files - a.material.unmapped_files);
  const mapping: ReviewItem[] = (data?.review ?? []).filter((r) => r.kind === "NEEDS_MAPPING");
  const decisions = (data?.review ?? []).filter(
    (r) => r.kind !== "NEEDS_MAPPING" && r.kind !== "PROPOSED_MOVE",
  );

  return (
    <>
      <PageHead
        eyebrow="Library"
        title="Intake"
        lead="What entered Continuum, and help identifying it. Nothing here writes to your Vault - importing and moving stay your decision."
        aside={
          data ? (
            <ActionButton
              action={refreshIntakeAction}
              label="Re-read intake"
              busyLabel="Reading intake…"
            />
          ) : null
        }
      />

      {error ? <ApiDown message={error} /> : null}

      {data ? (
        <>
          {SECTIONS.map((section) => {
            const list = units.filter((u) => u.section === section.key);
            if (!list.length) return null;
            return (
              <section key={section.key} className="block" aria-labelledby={`s-${section.key}`}>
                <div className="block-head">
                  <h2 id={`s-${section.key}`}>
                    {section.title}
                    <small>{section.note}</small>
                  </h2>
                  <span className="muted tabular">{list.length}</span>
                </div>
                <div className="list">
                  {list.slice(0, 50).map((unit) => (
                    <UnitItem key={`${unit.source}/${unit.unit}/${unit.path}`} unit={unit} />
                  ))}
                </div>
              </section>
            );
          })}

          {!units.length ? (
            <Empty title="Intake is empty">
              <p>
                Files you download land in your intake folders. Re-read intake after a download and
                they are identified here before anything reaches the Vault.
              </p>
            </Empty>
          ) : null}

          {uncatalogued.length ? (
            <section className="block" id="mapping" aria-labelledby="uncatalogued">
              <div className="block-head">
                <h2 id="uncatalogued">
                  Uncatalogued local material
                  <small>already in your Vault, not matched to a work</small>
                </h2>
              </div>
              <div className="list">
                {uncatalogued.map(({ family, material }) => (
                  <Link
                    key={`${family.id}-${material.material_class}`}
                    className="list-item"
                    href={`/library/acquisition/families/${encodeURIComponent(family.id)}`}
                  >
                    <div>
                      <h3>{family.title}</h3>
                      <p className="sub">
                        {plural(material.unmapped_files, "file")} in {classLabel(material.material_class)}{" "}
                        could belong to{" "}
                        {material.needs_mapping
                          ? plural(material.needs_mapping, "catalogued work")
                          : "a work the catalogue doesn't have yet"}
                        .
                      </p>
                    </div>
                    <div className="side">
                      <span className="chip info">Needs mapping</span>
                    </div>
                  </Link>
                ))}
              </div>
              {mapping.length ? (
                <details className="disclosure" style={{ marginTop: 12 }}>
                  <summary>How to map them</summary>
                  <div className="disclosure-body">
                    <p style={{ marginTop: 0 }}>
                      Point the work at the folder that holds it, or move the files into the
                      work&apos;s own folder yourself. Continuum never moves them for you.
                    </p>
                  </div>
                </details>
              ) : null}
            </section>
          ) : null}

          {data.duplicates.length ? (
            <section className="block" aria-labelledby="duplicates">
              <div className="block-head">
                <h2 id="duplicates">
                  Duplicates<small>identical bytes in more than one place · nothing is deleted</small>
                </h2>
                <span className="muted tabular">{data.duplicates.length}</span>
              </div>
              <div className="list">
                {data.duplicates.slice(0, 20).map((d, index) => (
                  <div className="list-item" key={index}>
                    <div>
                      <h3>{String(d.family || "Across families")}</h3>
                      <p className="sub">{String(d.detail ?? "")}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {data.conflicts.length || data.proposed_moves.length ? (
            <section className="block" aria-labelledby="conflicts">
              <div className="block-head">
                <h2 id="conflicts">
                  Conflicts<small>things only you can decide</small>
                </h2>
              </div>
              <div className="list">
                {data.conflicts.slice(0, 20).map((c, index) => (
                  <div className="list-item" key={`c-${index}`}>
                    <div>
                      <h3>{String(c.family ?? "")}</h3>
                      <p className="sub">
                        {String(c.detail ?? "")} · <code>{String(c.path ?? "")}</code>
                      </p>
                    </div>
                  </div>
                ))}
                {data.proposed_moves.length ? (
                  <div className="list-item">
                    <div>
                      <h3>{plural(data.proposed_moves.length, "file")} may be in the wrong folder</h3>
                      <p className="sub">
                        Their own metadata names a different work. Moving them is up to you.
                      </p>
                      <details className="disclosure" style={{ marginTop: 8 }}>
                        <summary>Show files</summary>
                        <div className="disclosure-body">
                          {data.proposed_moves.slice(0, 40).map((m, index) => (
                            <p key={index} style={{ margin: "0 0 4px" }}>
                              <code>{basename(String(m.source ?? ""))}</code>{" "}
                              <span className="muted">{String(m.reason ?? "")}</span>
                            </p>
                          ))}
                        </div>
                      </details>
                    </div>
                  </div>
                ) : null}
              </div>
            </section>
          ) : null}

          {decisions.length ? (
            <section className="block" aria-labelledby="decisions">
              <details className="disclosure">
                <summary id="decisions">
                  {plural(decisions.length, "catalogue suggestion")} waiting for review
                </summary>
                <div className="disclosure-body list" style={{ marginTop: 12 }}>
                  {decisions.slice(0, 60).map((item, index) => (
                    <div className="list-item" key={`${item.kind}-${index}`}>
                      <div>
                        <h3>{item.item}</h3>
                        <p className="sub">
                          {item.family ? `${item.family} · ` : ""}
                          {item.detail}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            </section>
          ) : null}
        </>
      ) : null}
    </>
  );
}
