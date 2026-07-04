// ── Agent mode types ─────────────────────────────────────────────────────────

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

export interface AgentTraceEntry {
  call: AgentToolCall;
  result?: AgentToolResult;
}

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

export type AgentSSEEvent =
  | { type: "thinking"; content: string }
  | { type: "tool_call"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; success: boolean; output: unknown; error: string | null }
  | { type: "warning"; content: string }
  | { type: "token"; content: string }
  // session_id is now included so the frontend can pick up the session that
  // was created/reused server-side, exactly like chat mode's "done" event.
  | { type: "done"; content: string; iterations: number; session_id?: string }
  | { type: "iteration_limit"; content: string }
  | { type: "error"; content: string };

export type ChatMode = "chat" | "agent";
