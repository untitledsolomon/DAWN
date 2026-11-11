import { describe, it, expect } from "vitest";
import { applyUiEvent, finalizeLive, initialLiveDocs, type LiveDocsState } from "./stream";

describe("ui stream reducer", () => {
  it("accumulates blocks from ui events", () => {
    let s = applyUiEvent(initialLiveDocs, { type: "ui_start", ui_id: "x" });
    s = applyUiEvent(s, { type: "ui_block", ui_id: "x", index: 0, block: { type: "text", markdown: "hi" } });
    s = applyUiEvent(s, { type: "ui_block", ui_id: "x", index: 1, block: { type: "stat", label: "a", value: 1 } });
    expect(s.docs.x.blocks).toHaveLength(2);
    expect((s.docs.x.blocks[0] as any).type).toBe("text");
    expect((s.docs.x.blocks[1] as any).value).toBe(1);
  });

  it("out-of-order blocks fill their slot", () => {
    let s = applyUiEvent(initialLiveDocs, { type: "ui_start", ui_id: "x" });
    s = applyUiEvent(s, { type: "ui_block", ui_id: "x", index: 3, block: { type: "stat", label: "a", value: 1 } });
    expect((s.docs.x.blocks[3] as any).type).toBe("stat");
    expect(s.docs.x.blocks[0]).toBeUndefined();
  });

  it("counts block errors without breaking the doc", () => {
    let s = applyUiEvent(initialLiveDocs, { type: "ui_start", ui_id: "x" });
    s = applyUiEvent(s, { type: "ui_block_error", ui_id: "x", index: 0, error: "unknown type" });
    expect(s.docs.x.errorCount).toBe(1);
  });

  it("finalizeLive clears all drafts", () => {
    let s: LiveDocsState = applyUiEvent(initialLiveDocs, { type: "ui_start", ui_id: "x" });
    s = applyUiEvent(s, { type: "ui_block", ui_id: "x", index: 0, block: { type: "text", markdown: "m" } });
    s = finalizeLive();
    expect(s.order).toHaveLength(0);
    expect(Object.keys(s.docs)).toHaveLength(0);
  });
});
