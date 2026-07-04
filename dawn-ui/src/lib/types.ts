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

// Session types
export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface SessionMessage {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  tool_calls?: ToolCall[] | null;
  node_ids?: string[] | null;
  node_titles?: string[] | null;
  created_at: string;
}

// SSE event payloads
export type SSEEvent =
  | { type: "thinking"; content: string }
  | { type: "tool"; name: string; args: Record<string, unknown>; result_count: number }
  | { type: "context"; node_ids: string[]; node_titles: string[] }
  | { type: "token"; content: string }
  | { type: "done"; node_ids: string[]; node_titles: string[]; session_id?: string }
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

// Settings
export interface AppSettings {
  model: "deepseek" | "local";
  local_endpoint: string;
  theme: "light" | "dark" | "system";
  font_size: "s" | "m" | "l";
  deepseek_api_key: string;
  [key: string]: unknown;
}

export interface NotificationPrefs {
  agent_complete: boolean;
  ingestion_finished: boolean;
  graph_updates: boolean;
  system_alerts: boolean;
  [key: string]: boolean;
}

// Agent logs
export interface AgentLogEntry {
  id: string;
  session_id?: string;
  status: "success" | "error" | "running";
  task: string;
  tools_used: string[];
  duration_ms?: number;
  tokens_used: number;
  model: string;
  error_message?: string;
  trace?: Record<string, unknown>;
  created_at: string;
  completed_at?: string;
}

// v3.0: SSH
export interface SSHHost {
  id: string;
  label: string;
  hostname: string;
  port: number;
  username: string;
  auth_method: "key" | "password";
  tags: string[];
  notes: string | null;
  is_active: boolean;
  last_connected_at: string | null;
  created_at: string;
}

// v5.0: OSINT
export interface OSINTTarget {
  id: string;
  target_type: "domain" | "ip" | "email" | "username" | "organization";
  value: string;
  label: string | null;
  tags: string[];
  is_active: boolean;
  created_at: string;
}

export interface OSINTResult {
  id: string;
  target_id: string;
  scan_type: string;
  summary: string | null;
  severity: string | null;
  findings_count: number;
  created_at: string;
}

// v6.0: Pentesting
export interface PentestTarget {
  id: string;
  target: string;
  target_type: "ip" | "cidr" | "domain" | "url";
  label: string | null;
  authorized: boolean;
  tags: string[];
  created_at: string;
}

export interface VulnerabilityFinding {
  id: string;
  cve_id: string | null;
  title: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  status: "open" | "in_progress" | "resolved" | "false_positive" | "accepted_risk";
  created_at: string;
}

// v7.0: Books
export interface Book {
  id: string;
  title: string;
  author: string | null;
  category: string | null;
  tags: string[];
  ingested: boolean;
  ingestion_status: "pending" | "ingesting" | "complete" | "error";
  summary: string | null;
  created_at: string;
}

// v10.0: Integrations
export interface Integration {
  id: string;
  service_name: string;
  display_name: string;
  description: string;
  is_connected: boolean;
  last_sync_at: string | null;
  sync_status: string;
}

// v13.0: Monitoring
export interface MonitorStatus {
  targets: {
    id: string;
    name: string;
    latest_check: {
      status: "up" | "down" | "degraded";
      response_time_ms: number;
      checked_at: string;
    } | null;
  }[];
  summary: {
    total: number;
    up: number;
    down: number;
    healthy: boolean;
  };
}

export interface AlertEvent {
  id: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string | null;
  acknowledged: boolean;
  created_at: string;
}

// v16.0: Agent Tasks
export interface AgentTask {
  id: string;
  goal: string;
  status: "pending" | "running" | "paused" | "completed" | "failed" | "cancelled";
  progress: number;
  iterations: number;
  tools_used: string[];
  created_at: string;
}

export * from "./agent-types";
