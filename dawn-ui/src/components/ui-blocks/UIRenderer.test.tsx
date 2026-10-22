import { describe, it, expect } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import UIRenderer from "./UIRenderer";
import type { UIDoc } from "@/lib/ui/schema";

function html(doc: UIDoc): string {
  return renderToStaticMarkup(createElement(UIRenderer, { doc }));
}

describe("UIRenderer", () => {
  it("renders a stat row and a table from a normalized doc", () => {
    const doc: UIDoc = {
      v: 1,
      title: "Open issues",
      blocks: [
        { type: "stat", label: "Axis", value: 12 },
        {
          type: "table",
          columns: [{ key: "repo", label: "Repo" }, { key: "count", label: "Count" }],
          rows: [{ repo: "Axis", count: 12 }],
        },
      ],
    };
    const out = html(doc);
    expect(out).toContain("Open issues");
    expect(out).toContain("Axis");
    expect(out).toContain("<td");
    expect(out).toContain("12");
  });

  it("isolates a bad block from the rest", () => {
    const doc: UIDoc = {
      v: 1,
      title: "test",
      blocks: [
        // malformed: no type discriminator the dispatcher handles — unknown type
        { id: "x", value: 1 } as never,
        { type: "text", markdown: "survives" },
      ],
    };
    const out = html(doc);
    // The unknown block yields a nothing/fallback; the text block still renders.
    expect(out).toContain("survives");
    expect(out).not.toContain("Couldn't render this block");
  });

  it("renders a callout tone", () => {
    const out = html({
      v: 1,
      title: "",
      blocks: [{ type: "callout", tone: "danger", text: "careful" }],
    });
    expect(out).toContain("careful");
  });
});
