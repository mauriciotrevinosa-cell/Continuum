import type { SourceOut } from "@/lib/api";

/**
 * "Find this on my sources": one link per registered source that publishes a
 * search endpoint, aimed at the exact title.
 *
 * These are LINKS. The browser opens the source's own search; Continuum
 * never fetches, never signs in and never downloads from them. A source that
 * costs money is labelled, so the choice to spend is made before the click,
 * not after.
 */

const CJK = /[぀-ヿ㐀-鿿]/;
const COSTS = new Set([
  "SUBSCRIPTION_WEB",
  "PAID_WEB",
  "DRM_EBOOK",
  "DRM_FREE_PURCHASE",
  "PHYSICAL_ONLY",
]);

/**
 * Registered source metadata is user-controlled data. Only web URLs are ever
 * rendered as clickable search links; malformed templates and non-web schemes
 * stay inert instead of becoming navigation/execution surfaces in the UI.
 */
function searchHref(template: string, query: string): string | null {
  try {
    const href = template.replace("{q}", encodeURIComponent(query));
    const url = new URL(href);
    if (url.protocol !== "https:" && url.protocol !== "http:") return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function SourceSearch({
  titles,
  sources,
  missing,
}: {
  titles: string[];
  sources: SourceOut[];
  missing?: string;
}) {
  const searchable = sources.filter(
    (source) => source.enabled && source.search && source.search.includes("{q}"),
  );
  if (!searchable.length || !titles.length) return null;

  const english = titles[0];
  const japanese = titles.find((title) => CJK.test(title));

  const queryFor = (source: SourceOut): string =>
    source.languages.includes("ja") && japanese ? japanese : english;

  const links = searchable.flatMap((source) => {
    const query = queryFor(source);
    const href = searchHref(source.search!, query);
    return href ? [{ source, query, href }] : [];
  });

  if (!links.length) return null;

  return (
    <details className="finder">
      <summary>Find on my sources ({links.length})</summary>
      <p className="row-meta">
        Opens each source&apos;s own search in your browser. Continuum does not fetch, sign in or
        download from them.
        {missing ? ` Look for chapters ${missing}.` : ""}
      </p>
      <div className="pills">
        {links.map(({ source, query, href }) => (
          <a
            key={source.id}
            className="pill accent"
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            title={`Search ${source.name} for "${query}"`}
          >
            {source.name}
            {source.access.some((model) => COSTS.has(model)) ? " · paid" : ""}
          </a>
        ))}
      </div>
      <p className="row-meta">
        Searching for: <code>{english}</code>
        {japanese ? (
          <>
            {" "}
            · Japanese stores: <code>{japanese}</code>
          </>
        ) : null}
      </p>
    </details>
  );
}
