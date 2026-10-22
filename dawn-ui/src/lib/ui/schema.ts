// TS mirror of the Intelligent UI document schema (server: dawn-api/ui/schema.py).
// The server normalizes and validates; these types describe what the frontend
// renders. The `chart` block carries `vega_spec`, which the server builds.

export type Tone = "info" | "warn" | "danger" | "success";

export interface Action {
  kind: "prompt" | "navigate" | "tool";
  text?: string;
  to?: string;
  tool?: string;
  args?: Record<string, unknown>;
  inputs?: string[];
}

interface BaseBlock {
  id?: string;
}

export interface TextBlock extends BaseBlock { type: "text"; markdown: string }
export interface CalloutBlock extends BaseBlock { type: "callout"; tone?: Tone; title?: string; text: string }
export interface StatBlock extends BaseBlock {
  type: "stat"; label: string; value: string | number; unit?: string;
  delta?: { value: number; direction: "up" | "down" | "flat"; good?: "up" | "down" };
  hint?: string;
}
export interface TableBlock extends BaseBlock {
  type: "table";
  columns?: { key: string; label: string; type?: string; align?: string }[];
  rows: Record<string, unknown>[];
  sortable?: boolean;
  caption?: string;
}
export interface ChartBlock extends BaseBlock {
  type: "chart";
  chart_type: string;
  data: Record<string, unknown>[];
  x_field: string;
  y_field: string;
  color_field?: string;
  title?: string;
  vega_spec?: Record<string, unknown>;
}
export interface KeyValueItem { label: string; value: string }
export interface KeyValueBlock extends BaseBlock { type: "key_value"; items: KeyValueItem[] }
export interface CodeBlock extends BaseBlock { type: "code"; language?: string; text: string }
export interface TimelineItem {
  time: string; title: string; detail?: string;
  status?: "done" | "active" | "pending" | "failed";
}
export interface TimelineBlock extends BaseBlock { type: "timeline"; items: TimelineItem[] }
export interface ButtonBlock extends BaseBlock { type: "button"; label: string; variant?: "primary" | "default"; action: Action }

export interface CalcInput {
  id: string; label: string; kind?: "number" | "slider" | "text" | "select" | "toggle";
  default?: unknown; min?: number; max?: number; step?: number; unit?: string; options?: string[];
}
export interface CalcOutput { label: string; expr: string; format?: string }
export interface CalcBlock extends BaseBlock { type: "calc"; inputs: CalcInput[]; outputs: CalcOutput[]; note?: string }

export interface FormField {
  id: string; label: string; kind?: "text" | "number" | "select" | "toggle";
  default?: unknown; options?: string[]; required?: boolean;
}
export interface FormBlock extends BaseBlock { type: "form"; fields: FormField[]; submit: { label?: string; action: Action } }
export interface ApprovalBlock extends BaseBlock { type: "approval"; pending_action_id?: string }
export interface EmbedBlock extends BaseBlock { type: "embed"; code: string; title?: string }

export type LeafBlock =
  | TextBlock | CalloutBlock | StatBlock | TableBlock | ChartBlock
  | KeyValueBlock | CodeBlock | TimelineBlock | ButtonBlock
  | CalcBlock | FormBlock | ApprovalBlock | EmbedBlock;

export interface ColumnsBlock extends BaseBlock { type: "columns"; children: LeafBlock[] }
export interface TabsBlock extends BaseBlock { type: "tabs"; tabs: { label: string; children: LeafBlock[] }[] }

export type Block = LeafBlock | ColumnsBlock | TabsBlock;

export interface UIDoc {
  v: number;
  title: string;
  blocks: Block[];
  _meta?: { blocks: number; normalized: number; dropped: number; unverified_sources?: number };
}

// Limits (mirror of the server) — used by the streaming reducer to guard state.
export const MAX_TOP_LEVEL_BLOCKS = 40;
