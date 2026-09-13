/**
 * Markdown rendered as studio typography.
 *
 * A small, deliberate subset - headings, paragraphs, emphasis, inline and
 * fenced code, lists, block quotes, rules, simple tables and web links -
 * turned into React elements. No HTML in the source is ever passed through,
 * and only http(s) and mailto links become links, so a document can style
 * text but can never inject markup or script.
 *
 * Headings get stable ids so a document outline can link to them.
 */
import type { ReactNode } from "react";

export interface Heading {
  depth: number;
  text: string;
  id: string;
}

type Block =
  | { kind: "heading"; depth: number; text: string; id: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; text: string; lang: string }
  | { kind: "quote"; blocks: Block[] }
  | { kind: "list"; ordered: boolean; start: number; items: Block[][] }
  | { kind: "rule" }
  | { kind: "table"; header: string[]; rows: string[][] };

function slugify(text: string, used: Map<string, number>): string {
  const base =
    text
      .toLowerCase()
      .replace(/[`*_~]/g, "")
      .replace(/[^\p{L}\p{N}]+/gu, "-")
      .replace(/^-+|-+$/g, "") || "section";
  const count = used.get(base) ?? 0;
  used.set(base, count + 1);
  return count ? `${base}-${count}` : base;
}

const LIST_ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

function parseBlocks(lines: string[], used: Map<string, number>): Block[] {
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    const fence = /^(\s*)(`{3,}|~{3,})\s*([\w-]*)\s*$/.exec(line);
    if (fence) {
      const marker = fence[2];
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(marker)) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1;
      blocks.push({ kind: "code", text: body.join("\n"), lang: fence[3] });
      continue;
    }
    const heading = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (heading) {
      const text = heading[2];
      blocks.push({ kind: "heading", depth: heading[1].length, text, id: slugify(text, used) });
      i += 1;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      blocks.push({ kind: "rule" });
      i += 1;
      continue;
    }
    if (/^\s*>/.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      blocks.push({ kind: "quote", blocks: parseBlocks(quoted, used) });
      continue;
    }
    if (
      /^\s*\|.*\|\s*$/.test(line) &&
      i + 1 < lines.length &&
      /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/.test(lines[i + 1])
    ) {
      const cells = (row: string) =>
        row
          .trim()
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((c) => c.trim());
      const header = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(cells(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }
    const item = LIST_ITEM.exec(line);
    if (item) {
      const indent = item[1].length;
      const ordered = /\d/.test(item[2]);
      const start = ordered ? Number.parseInt(item[2], 10) : 1;
      const items: Block[][] = [];
      while (i < lines.length) {
        const current = LIST_ITEM.exec(lines[i]);
        if (!current || current[1].length !== indent || /\d/.test(current[2]) !== ordered) break;
        const content: string[] = [current[3]];
        i += 1;
        while (i < lines.length) {
          const next = lines[i];
          const nested = LIST_ITEM.exec(next);
          if (nested && nested[1].length <= indent) break;
          if (!next.trim()) {
            const after = lines[i + 1];
            if (after === undefined || !/^\s+\S/.test(after) || (LIST_ITEM.exec(after)?.[1].length ?? 99) <= indent) break;
            content.push("");
            i += 1;
            continue;
          }
          if (!nested && !/^\s+/.test(next)) break;
          content.push(next.slice(Math.min(next.length - next.trimStart().length, indent + 2)));
          i += 1;
        }
        items.push(parseBlocks(content, used));
      }
      blocks.push({ kind: "list", ordered, start, items });
      continue;
    }
    const paragraph: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6})\s/.test(lines[i]) &&
      !/^\s*(`{3,}|~{3,})/.test(lines[i]) &&
      !/^\s*>/.test(lines[i]) &&
      !LIST_ITEM.test(lines[i]) &&
      !/^\s*([-*_])(\s*\1){2,}\s*$/.test(lines[i])
    ) {
      paragraph.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: paragraph.join("\n") });
  }
  return blocks;
}

function safeHref(href: string): string | null {
  try {
    const url = new URL(href);
    return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

/** Inline markup: `code`, **bold**, *emphasis*, [links](https://...), hard breaks. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(`+)([\s\S]*?)\1|\*\*([\s\S]+?)\*\*|__([\s\S]+?)__|\*([^*\n]+?)\*|_([^_\n]+?)_|\[([^\]]+)\]\(([^)\s]+)\)| {2,}\n|\n/g;
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(pattern)) {
    const at = match.index ?? 0;
    if (at > last) out.push(text.slice(last, at));
    const key = `${keyPrefix}-${n++}`;
    if (match[1]) out.push(<code key={key}>{match[2]}</code>);
    else if (match[3] !== undefined || match[4] !== undefined)
      out.push(<strong key={key}>{inline(match[3] ?? match[4], key)}</strong>);
    else if (match[5] !== undefined || match[6] !== undefined)
      out.push(<em key={key}>{inline(match[5] ?? match[6], key)}</em>);
    else if (match[7] !== undefined) {
      const href = safeHref(match[8]);
      out.push(
        href ? (
          <a key={key} href={href} target="_blank" rel="noreferrer noopener">
            {inline(match[7], key)}
          </a>
        ) : (
          <span key={key}>{inline(match[7], key)}</span>
        ),
      );
    } else if (match[0].startsWith("  ")) out.push(<br key={key} />);
    else out.push(" ");
    last = at + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function render(blocks: Block[], prefix: string): ReactNode[] {
  return blocks.map((block, index) => {
    const key = `${prefix}${index}`;
    switch (block.kind) {
      case "heading": {
        const Tag = `h${Math.min(block.depth + 1, 6)}` as "h2";
        return (
          <Tag key={key} id={block.id}>
            {inline(block.text, key)}
          </Tag>
        );
      }
      case "paragraph":
        return <p key={key}>{inline(block.text, key)}</p>;
      case "code":
        return (
          <pre key={key} className={block.lang === "text" ? "diagram" : undefined}>
            <code>{block.text}</code>
          </pre>
        );
      case "quote":
        return <blockquote key={key}>{render(block.blocks, `${key}q`)}</blockquote>;
      case "rule":
        return <hr key={key} />;
      case "table":
        return (
          <div className="table-wrap" key={key}>
            <table>
              <thead>
                <tr>
                  {block.header.map((cell, c) => (
                    <th key={c}>{inline(cell, `${key}h${c}`)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r}>
                    {row.map((cell, c) => (
                      <td key={c}>{inline(cell, `${key}r${r}c${c}`)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      case "list": {
        const items = block.items.map((item, n) => {
          const only = item.length === 1 && item[0].kind === "paragraph" ? item[0] : null;
          return (
            <li key={n}>{only ? inline(only.text, `${key}i${n}`) : render(item, `${key}i${n}-`)}</li>
          );
        });
        return block.ordered ? (
          <ol key={key} start={block.start}>
            {items}
          </ol>
        ) : (
          <ul key={key}>{items}</ul>
        );
      }
      default:
        return null;
    }
  });
}

export function parseMarkdown(source: string): { blocks: Block[]; headings: Heading[] } {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks = parseBlocks(lines, new Map());
  const headings: Heading[] = [];
  const walk = (list: Block[]) => {
    for (const block of list) {
      if (block.kind === "heading") headings.push({ depth: block.depth, text: block.text, id: block.id });
    }
  };
  walk(blocks);
  return { blocks, headings };
}

const FIELD = /^\*\*([^*]{1,40}?):\*\*\s*(.*?)\s*\\?$/;

/**
 * The author's field block - consecutive ``**Key:** value`` lines directly
 * under the title - and how many blocks it and the title occupy. Fields are
 * the author's words, shown as written; nothing reads meaning into them.
 */
function leading(blocks: Block[]): { fields: [string, string][]; skip: number } {
  const title = blocks[0]?.kind === "heading" && blocks[0].depth === 1 ? 1 : 0;
  const next = blocks[title];
  if (next?.kind !== "paragraph") return { fields: [], skip: title };
  const lines = next.text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const fields = lines.map((line) => FIELD.exec(line));
  if (!lines.length || fields.some((m) => !m)) return { fields: [], skip: title };
  return { fields: fields.map((m) => [m![1].trim(), m![2]]), skip: title + 1 };
}

/** The author's leading fields of a document, e.g. [["Status", "draft"], ...]. */
export function documentFields(source: string): [string, string][] {
  return leading(parseMarkdown(source).blocks).fields;
}

/** A line of Markdown inline text: emphasis, code and safe links only. */
export function InlineText({ text }: { text: string }) {
  return <>{inline(text, "i")}</>;
}

/**
 * Renders a document. With ``asDocument`` the title and the author's field
 * block are left out, because the page shows both in its own header.
 */
export function Markdown({ source, asDocument = false }: { source: string; asDocument?: boolean }) {
  const { blocks } = parseMarkdown(source);
  const shown = asDocument ? blocks.slice(leading(blocks).skip) : blocks;
  return <div className="prose">{render(shown, "b")}</div>;
}

export function plainText(text: string): string {
  return text.replace(/[`*_]/g, "");
}
