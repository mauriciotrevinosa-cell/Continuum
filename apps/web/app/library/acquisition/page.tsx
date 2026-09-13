import Link from "next/link";
import { ApiUnreachableError, type AcquisitionOverview, type NextStep, acquisition } from "@/lib/api";
import { classLabel, formatBytes, plural, timeAgo } from "@/lib/acquisition";
import {
  ApiDown,
  CoverageBar,
  Empty,
  FamilyCard,
  Legend,
  coverageSegments,
} from "./_components/ui";
import { RefreshControl } from "./_components/RefreshControl";

export const dynamic = "force-dynamic";

function stepHref(step: NextStep): string | null {
  switch (step.kind) {
    case "map":
    case "finish":
    case "acquire":
      return step.family_id ? `/library/acquisition/families/${encodeURIComponent(step.family_id)}` : null;
    case "update":
      return "/library/acquisition/updates";
    case "intake":
    case "review":
      return "/library/acquisition/intake";
    default:
      return null;
  }
}

function glyph(materialClass: string): string {
  const label = classLabel(materialClass);
  return label.slice(0, 2).toUpperCase();
}

export default async function OverviewPage() {
  let data: AcquisitionOverview | null = null;
  let error: string | null = null;
  try {
    data = await acquisition.overview();
  } catch (cause) {
    error = cause instanceof ApiUnreachableError ? cause.message : String(cause);
  }

  const head = (
    <header className="page-head">
      <div>
        <p className="eyebrow">Library</p>
        <h1 className="title xl">Acquisition</h1>
        <p className="lead">See what your Library contains, what is incomplete, and what changed.</p>
      </div>
    </header>
  );

  if (error || !data) {
    return (
      <>
        {head}
        <ApiDown message={error ?? "no response"} />
      </>
    );
  }

  const { hero, status } = data;

  if (!status.available || status.freshness.state === "empty") {
    return (
      <>
        {head}
        <Empty
          title="Your Library is empty so far"
          actions={status.cli_available ? <RefreshControl variant="primary" /> : null}
        >
          <p>
            Continuum reads what the acquisition engine records about your Vault. Once it has scanned
            your Vault, your families appear here - nothing is assumed or filled in for you.
          </p>
        </Empty>
      </>
    );
  }

  const segments = coverageSegments(hero);
  const attention = [...data.families]
    .filter((f) => f.attention > 0 || f.stale)
    .sort((a, b) => b.attention - a.attention || a.title.localeCompare(b.title))
    .slice(0, 6);
  const showcase = attention.length
    ? attention
    : [...data.families].sort((a, b) => b.bytes - a.bytes).slice(0, 6);

  return (
    <>
      {head}

      <section className="hero" aria-label="Library summary">
        <div className="surface hero-main">
          <p className="eyebrow">Library coverage</p>
          <div className="hero-figures">
            <div className="figure">
              <span className="n">{hero.families}</span>
              <span className="l">{hero.families === 1 ? "family" : "families"}</span>
            </div>
            <div className="figure">
              <span className="n">{formatBytes(hero.bytes)}</span>
              <span className="l">{plural(hero.files, "file")}</span>
            </div>
            <div className="figure">
              <span className="n">{hero.complete + hero.present}</span>
              <span className="l">story works held</span>
            </div>
            <div className="figure">
              <span className="n">{hero.partial}</span>
              <span className="l">partial</span>
            </div>
            <div className={`figure${hero.attention_families ? " attention" : ""}`}>
              <span className="n">{hero.attention_families}</span>
              <span className="l">need attention</span>
            </div>
          </div>
          <CoverageBar segments={segments} label="Story works" />
          <Legend segments={segments} />
          <p className="hero-note">
            Counted over {plural(hero.story_works, "story work")}: main series, sequels, spin-offs,
            adaptations and novels. Guidebooks, art books and other supplements are shown per
            family.
          </p>
        </div>

        <aside className="surface recent" aria-labelledby="recently-added">
          <h2 id="recently-added">Recently added</h2>
          {data.recently_added.length ? (
            data.recently_added.map((item) => (
              <Link
                key={`${item.family_id}-${item.material_class}`}
                className="recent-item"
                href={`/library/acquisition/families/${encodeURIComponent(item.family_id)}`}
              >
                <span className={`glyph${item.video_files ? " video" : ""}`} aria-hidden>
                  {glyph(item.material_class)}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="name">{item.family}</span>
                  <br />
                  <span className="meta">
                    {classLabel(item.material_class)} ·{" "}
                    {item.video_files ? plural(item.video_files, "video file") : plural(item.files, "file")}{" "}
                    · {formatBytes(item.bytes)}
                  </span>
                </span>
                <span className="when">{timeAgo(item.last_added_at)}</span>
              </Link>
            ))
          ) : (
            <p className="muted" style={{ margin: 0 }}>
              Nothing new in the last 30 days.
            </p>
          )}
        </aside>
      </section>

      {data.next_steps.length ? (
        <section className="block" aria-labelledby="next">
          <div className="block-head">
            <h2 id="next">Continue building your Library</h2>
          </div>
          <div className="steps">
            {data.next_steps.map((step, index) => {
              const href = stepHref(step);
              const body = (
                <>
                  <span className="step-mark" aria-hidden />
                  <span>
                    <h3>{step.title}</h3>
                    {step.detail ? <p>{step.detail}</p> : null}
                  </span>
                </>
              );
              return href ? (
                <Link key={index} href={href} className={`step ${step.tone}`}>
                  {body}
                </Link>
              ) : (
                <div key={index} className={`step ${step.tone}`}>
                  {body}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      <section className="block" aria-labelledby="families">
        <div className="block-head">
          <h2 id="families">
            Families
            <small>{attention.length ? "needing attention first" : "largest first"}</small>
          </h2>
          <Link className="more" href="/library/acquisition/families">
            All {hero.families} families →
          </Link>
        </div>
        <div className="collection">
          {showcase.map((family) => (
            <FamilyCard key={family.id} family={family} />
          ))}
        </div>
      </section>
    </>
  );
}
