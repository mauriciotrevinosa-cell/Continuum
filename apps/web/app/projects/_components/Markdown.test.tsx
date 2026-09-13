import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Markdown, documentFields, parseMarkdown } from "./Markdown";

const html = (source: string) => renderToStaticMarkup(<Markdown source={source} />);

describe("Markdown", () => {
  it("renders the studio subset", () => {
    const out = html(
      "# Title\n\n**Status:** draft  \nnext line\n\n## Part one\n\n- a\n- **b**\n\n1. first\n2. second\n\n> quoted\n\n```text\nA -> B\n```\n\n---\n\n| x | y |\n|---|---|\n| 1 | 2 |\n",
    );
    expect(out).toContain('<h2 id="title">Title</h2>');
    expect(out).toContain("<strong>Status:</strong> draft<br/>next line");
    expect(out).toContain('<h3 id="part-one">Part one</h3>');
    expect(out).toContain("<ul><li>a</li><li><strong>b</strong></li></ul>");
    expect(out).toContain('<ol start="1"><li>first</li><li>second</li></ol>');
    expect(out).toContain("<blockquote><p>quoted</p></blockquote>");
    expect(out).toContain('<pre class="diagram"><code>A -&gt; B</code></pre>');
    expect(out).toContain("<hr/>");
    expect(out).toContain("<td>1</td>");
  });

  it("never passes HTML or script through", () => {
    const out = html('<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[x](javascript:alert(1)) [y](data:text/html,hi)');
    expect(out).not.toContain("<script");
    expect(out).not.toContain("<img");
    expect(out).not.toContain("javascript:");
    expect(out).not.toContain('href="data:');
    expect(out).toContain("&lt;script&gt;");
  });

  it("links only to the web", () => {
    const out = html("[site](https://example.invalid/page) and [mail](mailto:a@example.invalid)");
    expect(out).toContain('href="https://example.invalid/page"');
    expect(out).toContain('href="mailto:a@example.invalid"');
  });

  it("gives headings stable, unique ids for the outline", () => {
    const { headings } = parseMarkdown("# A\n\n## Scene\n\n## Scene\n");
    expect(headings.map((h) => h.id)).toEqual(["a", "scene", "scene-1"]);
  });

  it("lifts the author's field block into the document header", () => {
    const source = "# Episode\n\n**Status:** approved structure  \n**Date:** 2026-01-02\n\nBody text.\n";
    expect(documentFields(source)).toEqual([
      ["Status", "approved structure"],
      ["Date", "2026-01-02"],
    ]);
    const out = renderToStaticMarkup(<Markdown source={source} asDocument />);
    expect(out).not.toContain("Episode");
    expect(out).not.toContain("Status");
    expect(out).toContain("<p>Body text.</p>");
    expect(documentFields("# T\n\n**Status:** x\nnot a field\n")).toEqual([]);
  });
});
