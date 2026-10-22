// Reducer for the Intelligent UI streaming events (ui_start/ui_block/…).
// It accumulates the blocks of each live document; when the final `artifact`
// event for a ui document arrives the caller swaps the live draft for the
// stored artifact (finalizeLive clears every live draft).

import type { Block } from "./schema";

export interface LiveDoc {
  uiId: string;
  title?: string;
  blocks: Block[];
  errorCount: number;
}

export interface LiveDocsState {
  docs: Record<string, LiveDoc>;
  order: string[];
}

export const initialLiveDocs: LiveDocsState = { docs: {}, order: [] };

export type UiLiveEvent =
  | { type: "ui_start"; ui_id: string }
  | { type: "ui_block"; ui_id: string; index: number; block: unknown }
  | { type: "ui_block_error"; ui_id: string; index: number; error: string }
  | { type: "ui_end"; ui_id: string; index?: number };

export function applyUiEvent(state: LiveDocsState, ev: UiLiveEvent): LiveDocsState {
  switch (ev.type) {
    case "ui_start": {
      if (state.docs[ev.ui_id]) return state;
      return {
        docs: { ...state.docs, [ev.ui_id]: { uiId: ev.ui_id, blocks: [], errorCount: 0 } },
        order: [...state.order, ev.ui_id],
      };
    }
    case "ui_block": {
      const doc = state.docs[ev.ui_id];
      if (!doc) return state;
      const blocks = [...doc.blocks];
      blocks[ev.index] = ev.block as Block;
      return { ...state, docs: { ...state.docs, [ev.ui_id]: { ...doc, blocks } } };
    }
    case "ui_block_error": {
      const doc = state.docs[ev.ui_id];
      if (!doc) return state;
      return {
        ...state,
        docs: { ...state.docs, [ev.ui_id]: { ...doc, errorCount: doc.errorCount + 1 } },
      };
    }
    case "ui_end":
    default:
      return state;
  }
}

/** Drop all live drafts — a persisted ui artifact is now authoritative. */
export function finalizeLive(): LiveDocsState {
  return initialLiveDocs;
}
