import { describe, it, expect } from "vitest";
import { createElement, Fragment } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { renderMarkdown } from "./markdown";

// Render markdown to static HTML so the tests assert what the DOM would show.
function html(text: string): string {
  return renderToStaticMarkup(createElement(Fragment, null, renderMarkdown(text)));
}

describe("renderMarkdown", () => {
  it("renders bold and italic", () => {
    const out = html("a **bold** and *italic*");
    expect(out).toContain("<strong>bold</strong>");
    expect(out).toContain("<em>italic</em>");
  });

  it("escapes raw HTML instead of injecting it", () => {
    const out = html('<img src=x onerror=alert(1)>');
    expect(out).not.toMatch(/<img/i);
    expect(out).toMatch(/&lt;img src=x onerror=alert\(1\)&gt;/);
  });

  it("allows https links and renders unsafe links as plain text", () => {
    const safe = html("[label](https://example.com)");
    expect(safe).toMatch(/<a href="https:\/\/example\.com"/);
    expect(safe).toMatch(/rel="noreferrer noopener"/);

    const unsafe = html("[label](http://example.com)");
    expect(unsafe).not.toMatch(/<a /);
    expect(unsafe).toContain("http://example.com");
  });

  it("renders fenced code blocks as code", () => {
    const out = html("```js\nconst x = 1;\n```");
    expect(out).toMatch(/<pre><code class="language-js">/);
    expect(out).toContain("const x = 1;");
  });

  it("inlines code without executing", () => {
    const out = html("use `dangerouslySetInnerHTML` here");
    expect(out).toMatch(/<code>dangerouslySetInnerHTML<\/code>/);
  });

  it("marks up lists and headings", () => {
    const out = html("- one\n- two");
    expect(out).toContain("<ul>");
    expect(out).toContain("<li>one</li>");
    expect(out).toContain("<li>two</li>");

    const head = html("## Heading two");
    expect(head).toContain("<h2>Heading two</h2>");
  });
});
