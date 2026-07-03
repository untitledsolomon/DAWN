export type NodeType = "concept" | "entity" | "process" | "fact" | "memory" | "document";
export type NodeStatus = "active" | "stale" | "archived" | "draft";
export type EdgeRelation =
  | "is_a" | "part_of" | "depends_on" | "produces"
  | "causes" | "requires" | "see_also" | "precedes"
  | "owned_by" | "related_to" | "contradicts" | "derived_from";

export interface DawnNode {
  id: string;
  title: string;
  type: NodeType;
  body?: string;
  status: NodeStatus;
  source: string;
  source_ref?: string;
  confidence: number;
  created_at: string;
  updated_at: string;
  tags?: string[];
}

export interface DawnEdge {
  id: string;
  from_node: string;
  to_node: string;
  relation: EdgeRelation;
  weight: number;
  note?: string;
}

export interface Tag {
  id: string;
  name: string;
  description?: string;
}

// Chat types
export type MessageRole = "user" | "assistant";

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result_count: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  tool_calls?: ToolCall[];
  node_ids?: string[];
  node_titles?: string[];
  timestamp: Date;
}

// SSE event payloads
export type SSEEvent =
  | { type: "thinking"; content: string }
  | { type: "tool"; name: string; args: Record<string, unknown>; result_count: number }
  | { type: "context"; node_ids: string[]; node_titles: string[] }
  | { type: "token"; content: string }
  | { type: "done"; node_ids: string[]; node_titles: string[] }
  | { type: "error"; message: string };

// Ingestion
export interface IngestionLog {
  id: string;
  source: string;
  source_ref: string;
  nodes_created: number;
  edges_created: number;
  status: string;
  error?: string;
  ingested_at: string;
}

export * from "./agent-types";
