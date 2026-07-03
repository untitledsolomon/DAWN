// ── Agent mode types ──────────────────────────────────────────────────────────
// Append these to the existing src/lib/types.ts — do not replace the file,
// these are additions alongside everything already there.

export interface AgentToolCall {
  name: string;
  args: Record<string, unknown>;
}

export interface AgentToolResult {
  name: string;
  success: boolean;
  output: unknown;
  error: string | null;
}

// One row in the agent's visible activity trace for a single assistant turn —
// distinct from ToolCall (graph-search tool calls in chat mode), since agent
// tool calls carry richer info (success/failure, arbitrary output) that the
// knowledge-graph ToolCallIndicator was never designed to show.
export interface AgentTraceEntry {
  call: AgentToolCall;
  result?: AgentToolResult;
}

// Standalone shape — deliberately NOT `extends ChatMessage` to avoid a
// circular type-only import between this file and types.ts (types.ts
// re-exports from here via `export * from "./agent-types"`, so importing
// ChatMessage back from types.ts here creates a cycle that TypeScript
// resolves inconsistently depending on module resolution settings).
//
// This is a superset covering BOTH chat-mode and agent-mode optional fields,
// because ChatWindow keeps one shared `messages` state array across the
// mode toggle — a single assistant message might carry tool_calls/node_ids
// (from chat mode) or trace/warning (from agent mode), never both at once,
// but the array's element type has to accommodate either.
export interface AgentChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  // chat-mode fields (knowledge-graph search)
  tool_calls?: { name: string; args: Record<string, unknown>; result_count: number }[];
  node_ids?: string[];
  node_titles?: string[];
  // agent-mode fields (real tool execution)
  trace?: AgentTraceEntry[];
  warning?: string;
}

// SSE event payloads for /agent/ — deliberately a separate union from SSEEvent
// (chat mode) rather than merged into it, since the two endpoints' event
// vocabularies only partially overlap (both have "thinking"/"token"/"done"/
// "error", but agent mode's shapes differ — e.g. "done" carries `content` +
// `iterations` here, not `node_ids`/`node_titles`).
export type AgentSSEEvent =
  | { type: "thinking"; content: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; success: boolean; output: unknown; error: string | null }
  | { type: "warning"; content: string }
  | { type: "token"; content: string }
  | { type: "done"; content: string; iterations: number }
  | { type: "iteration_limit"; content: string }
  | { type: "error"; content: string };

export type ChatMode = "chat" | "agent";