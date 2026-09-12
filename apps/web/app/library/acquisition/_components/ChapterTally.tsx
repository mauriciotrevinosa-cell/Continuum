/**
 * How many chapters exist, how many are held, and which are missing.
 *
 * The distinction this component exists to make: a missing NUMBER is not a
 * missing chapter. Series skip integers and insert decimals (57.5), so when
 * the count matches what the release lists, a hole in the numbering is
 * reported as exactly that - and never dressed up as a gap in the library.
 */
export function ChapterTally({
  held,
  total,
  latest,
  gaps,
  missing,
}: {
  held: number;
  total: number | null;
  latest?: number | null;
  gaps?: string;
  missing?: string;
}) {
  const known = total ?? (latest ? Math.round(latest) : null);
  if (!held && !known) return null;

  const complete = known !== null && held >= known;
  const percent = known ? Math.min(100, Math.round((held / known) * 100)) : null;

  return (
    <div className="tally">
      <p className="tally-head">
        <strong>{held}</strong>
        {known !== null ? <> of {known} chapters</> : <> chapters held · total unknown</>}
        {missing ? <span className="tally-missing">missing {missing}</span> : null}
        {!missing && gaps ? (
          <span className="tally-note">numbering skips {gaps} — nothing missing</span>
        ) : null}
      </p>
      {percent !== null ? (
        <div className="meter" role="img" aria-label={`${held} of ${known} chapters`}>
          <i className={complete ? "ok" : "warn"} style={{ width: `${percent}%` }} />
        </div>
      ) : null}
    </div>
  );
}
