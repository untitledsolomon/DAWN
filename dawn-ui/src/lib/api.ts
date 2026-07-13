import type { DawnNode, Tag, IngestionLog, SSEEvent, ChatSession, SessionMessage, AppSettings, NotificationPrefs, AgentLogEntry, Artifact } from "./types";
import type { AgentSSEEvent } from "./agent-types";

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

// ── Nodes ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function listNodes(params?: {
  status?: string;
  type?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}): Promise<DawnNode[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.type) qs.set("type", params.type);
  if (params?.tag) qs.set("tag", params.tag);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));

  const res = await fetch(`${BASE}/nodes/?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list nodes: ${res.status}`);
  return res.json();
}

export async function countNodes(params?: {
  status?: string;
  type?: string;
  tag?: string;
}): Promise<number> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.type) qs.set("type", params.type);
  if (params?.tag) qs.set("tag", params.tag);

  const res = await fetch(`${BASE}/nodes/count?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to count nodes: ${res.status}`);
  const data = await res.json();
  return data.total ?? 0;
}

export async function getNode(id: string) {
  const res = await fetch(`${BASE}/nodes/${id}`, { headers: headers() });
  if (!res.ok) throw new Error(`Node not found: ${id}`);
  return res.json();
}

export async function createNode(data: Partial<DawnNode> & { tags?: string[] }) {
  const res = await fetch(`${BASE}/nodes/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create node");
  return res.json();
}

export async function updateNode(id: string, data: Partial<DawnNode> & { tags?: string[] }) {
  const res = await fetch(`${BASE}/nodes/${id}`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to update node");
  return res.json();
}

export async function deleteNode(id: string) {
  await fetch(`${BASE}/nodes/${id}`, { method: "DELETE", headers: headers() });
}

export async function approveNode(id: string) {
  const res = await fetch(`${BASE}/nodes/${id}/approve`, { method: "POST", headers: headers() });
  return res.json();
}

export async function rejectNode(id: string) {
  const res = await fetch(`${BASE}/nodes/${id}/reject`, { method: "POST", headers: headers() });
  return res.json();
}

export async function getPendingNodes(): Promise<DawnNode[]> {
  const res = await fetch(`${BASE}/nodes/memory/pending`, { headers: headers() });
  return res.json();
}

// ── Tags ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function listTags(): Promise<Tag[]> {
  const res = await fetch(`${BASE}/nodes/tags`, { headers: headers() });
  return res.json();
}

export async function createTag(name: string, description?: string) {
  const res = await fetch(`${BASE}/nodes/tags`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ name, description }),
  });
  return res.json();
}

// ── Edges ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function createEdge(data: {
  from_node: string;
  to_node: string;
  relation: string;
  weight?: number;
  note?: string;
}) {
  const res = await fetch(`${BASE}/nodes/edges/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  return res.json();
}

// ── Search ──────────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function searchNodes(q: string, limit = 10): Promise<DawnNode[]> {
  const res = await fetch(`${BASE}/search/?q=${encodeURIComponent(q)}&limit=${limit}`, { headers: headers() });
  return res.json();
}

export async function traverseNode(nodeId: string, depth = 2) {
  const res = await fetch(`${BASE}/search/traverse/${nodeId}?depth=${depth}`, { headers: headers() });
  return res.json();
}

// ── Chat (streaming) ──────────────────────────────────────────────────────────────────────────────────────────────────

export async function* streamChat(
  message: string,
  history: { role: string; content: string }[],
  sessionId?: string,
  webSearchEnabled?: boolean,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/chat/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, history, session_id: sessionId, web_search_enabled: webSearchEnabled }),
  });

  if (!res.ok || !res.body) {
    yield { type: "error", message: `API error: ${res.status}` };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6)) as SSEEvent;
          yield event;
        } catch {
          // Malformed SSE line — skip
        }
      }
    }
  }
}

// ── Chat Sessions ─────────────────────────────────────────────────────────────────────────────────────────────────────

export async function listSessions(): Promise<ChatSession[]> {
  const res = await fetch(`${BASE}/chat/sessions`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  return res.json();
}

export async function createSession(title = "New Chat", mode: "chat" | "agent" | "visualize" = "chat"): Promise<ChatSession> {
  const res = await fetch(`${BASE}/chat/sessions`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ title, mode }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function getSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${BASE}/chat/sessions/${sessionId}`, { headers: headers() });
  if (!res.ok) throw new Error(`Session not found: ${sessionId}`);
  return res.json();
}

export async function updateSession(sessionId: string, title: string): Promise<ChatSession> {
  const res = await fetch(`${BASE}/chat/sessions/${sessionId}`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Failed to update session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await fetch(`${BASE}/chat/sessions/${sessionId}`, { method: "DELETE", headers: headers() });
}

export async function getSessionMessages(sessionId: string): Promise<SessionMessage[]> {
  const res = await fetch(`${BASE}/chat/sessions/${sessionId}/messages`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to get messages: ${res.status}`);
  return res.json();
}

// ── Settings ──────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function getSettings(): Promise<AppSettings> {
  const res = await fetch(`${BASE}/settings`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to get settings: ${res.status}`);
  return res.json();
}

export async function updateSetting(key: string, value: unknown): Promise<void> {
  const res = await fetch(`${BASE}/settings/${key}`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify({ value }),
  });
  if (!res.ok) throw new Error(`Failed to update setting: ${res.status}`);
}

// ── Notifications ─────────────────────────────────────────────────────────────────────────────────────────────────────

export async function getNotificationPrefs(): Promise<NotificationPrefs> {
  const res = await fetch(`${BASE}/notifications`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to get notification prefs: ${res.status}`);
  return res.json();
}

export async function updateNotificationPrefs(prefs: Partial<NotificationPrefs>): Promise<void> {
  const res = await fetch(`${BASE}/notifications`, {
    method: "PUT",
    headers: headers(),
    body: JSON.stringify(prefs),
  });
  if (!res.ok) throw new Error(`Failed to update notification prefs: ${res.status}`);
}

// ── Agent Logs ────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function getAgentLogs(limit = 50, statusFilter?: string): Promise<AgentLogEntry[]> {
  const qs = new URLSearchParams();
  qs.set("limit", String(limit));
  if (statusFilter) qs.set("status_filter", statusFilter);
  const res = await fetch(`${BASE}/agent-logs?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to get agent logs: ${res.status}`);
  return res.json();
}

export async function getAgentLog(logId: string): Promise<AgentLogEntry> {
  const res = await fetch(`${BASE}/agent-logs/${logId}`, { headers: headers() });
  if (!res.ok) throw new Error(`Agent log not found: ${logId}`);
  return res.json();
}

// ── Ingestion ─────────────────────────────────────────────────────────────────────────────────────────────────────────

export interface IngestFileResponse {
  status: string;
  job_id: string;
  title: string;
  file_type: string;
  filename: string;
  tags: string[];
  size_mb: number;
  note?: string | null;
}

export interface IngestUrlResponse {
  status: string;
  job_id: string;
  title: string;
  source_url: string;
  tags: string[];
}

export interface IngestJobStatus {
  job_id: string;
  type: string;
  status: "queued" | "running" | "success" | "failed";
  error?: string | null;
  result?: {
    title?: string;
    nodes_created?: number;
    edges_created?: number;
    sections?: number;
    file_type?: string;
  } | null;
  created_at: number;
  started_at?: number | null;
  completed_at?: number | null;
}

export interface IngestedDocument {
  id: string;
  title: string;
  type: string;
  body?: string;
  status: string;
  source: string;
  source_ref?: string;
  tags?: string[];
  created_at: string;
  updated_at: string;
}

export async function ingestRepo(repoPath: string, repoName: string, tags: string[] = []) {
  const res = await fetch(`${BASE}/ingest/repo`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ repo_path: repoPath, repo_name: repoName, tags }),
  });
  return res.json();
}

export async function ingestDocument(title: string, content: string, sourceRef = "", tags: string[] = []) {
  const res = await fetch(`${BASE}/ingest/document`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ title, content, source_ref: sourceRef, tags }),
  });
  return res.json();
}

export async function ingestFile(file: File, title: string, tags: string[] = []): Promise<IngestFileResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("tags", tags.join(","));
  const res = await fetch(`${BASE}/ingest/file`, {
    method: "POST",
    headers: { "x-api-key": KEY },
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export const ingestPdf = ingestFile;

export interface IngestFilesResponse {
  status: string;
  total_files: number;
  queued: number;
  errors: number;
  jobs: Array<{ job_id: string; filename: string; file_type: string; tags: string[]; size_mb: number }>;
  error_details: Array<{ file: string; error: string }> | null;
}

export async function ingestFiles(files: File[], tags: string[] = []): Promise<IngestFilesResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("tags", tags.join(","));
  const res = await fetch(`${BASE}/ingest/files`, {
    method: "POST",
    headers: { "x-api-key": KEY },
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function ingestUrl(sourceUrl: string, title?: string, tags: string[] = []): Promise<IngestUrlResponse> {
  const res = await fetch(`${BASE}/ingest/url`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ url: sourceUrl, title: title || "", tags }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "URL ingestion failed" }));
    throw new Error(err.detail || `URL ingestion failed: ${res.status}`);
  }
  return res.json();
}

export async function getIngestionStatus(jobId: string): Promise<IngestJobStatus> {
  const res = await fetch(`${BASE}/ingest/status/${jobId}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to get job status: ${res.status}`);
  return res.json();
}

export async function listIngestedDocuments(params?: {
  type?: string;
  tag?: string;
  limit?: number;
  offset?: number;
}): Promise<IngestedDocument[]> {
  const qs = new URLSearchParams();
  if (params?.type) qs.set("type", params.type);
  if (params?.tag) qs.set("tag", params.tag);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));
  const res = await fetch(`${BASE}/nodes/?${qs}&source=document`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list ingested documents: ${res.status}`);
  return res.json();
}

export async function getIngestedDocument(bookIdOrSourceRef: string): Promise<IngestedDocument> {
  // Books ingested via /books/{id}/ingest store source_ref = book UUID.
  // Books created from a direct file upload store source_ref = filename.
  // Callers should pass book.source_ref when available (falls back to
  // book.id, which is correct for the UUID-sourced case).
  const res = await fetch(`${BASE}/nodes/?source_ref=${encodeURIComponent(bookIdOrSourceRef)}&limit=1`, { headers: headers() });
  if (!res.ok) throw new Error(`Document not found: ${bookIdOrSourceRef}`);
  const nodes = await res.json();
  if (!Array.isArray(nodes) || nodes.length === 0) {
    throw new Error(`Document not found: ${bookIdOrSourceRef}`);
  }
  return nodes[0];
}

export async function deleteIngestedDocument(docId: string): Promise<void> {
  await fetch(`${BASE}/nodes/${docId}`, { method: "DELETE", headers: headers() });
}

export async function getIngestionLog(): Promise<IngestionLog[]> {
  const res = await fetch(`${BASE}/ingest/log`, { headers: headers() });
  return res.json();
}

// ── Health ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.json();
  } catch {
    return { status: "offline" };
  }
}

// ── v3.0: SSH Hosts ───────────────────────────────────────────────────────────────────────────────────────────────────

export async function listSSHHosts() {
  const res = await fetch(`${BASE}/ssh/hosts`, { headers: headers() });
  return res.json();
}

export async function createSSHHost(data: Record<string, unknown>) {
  const res = await fetch(`${BASE}/ssh/hosts`, {
    method: "POST", headers: headers(), body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteSSHHost(id: string) {
  await fetch(`${BASE}/ssh/hosts/${id}`, { method: "DELETE", headers: headers() });
}

// ── v5.0: OSINT ───────────────────────────────────────────────────────────────────────────────────────────────────────

export async function listOSINTTargets() {
  const res = await fetch(`${BASE}/osint/targets`, { headers: headers() });
  return res.json();
}

export async function createOSINTTarget(data: Record<string, unknown>) {
  const res = await fetch(`${BASE}/osint/targets`, {
    method: "POST", headers: headers(), body: JSON.stringify(data),
  });
  return res.json();
}

export async function deleteOSINTTarget(id: string) {
  await fetch(`${BASE}/osint/targets/${id}`, { method: "DELETE", headers: headers() });
}

// ── v6.0: Pentesting ──────────────────────────────────────────────────────────────────────────────────────────────────

export async function listPentestTargets() {
  const res = await fetch(`${BASE}/pentest/targets`, { headers: headers() });
  return res.json();
}

export async function listVulnerabilities(severity?: string, status?: string) {
  const qs = new URLSearchParams();
  if (severity) qs.set("severity", severity);
  if (status) qs.set("status", status);
  const res = await fetch(`${BASE}/pentest/vulnerabilities?${qs}`, { headers: headers() });
  return res.json();
}

// ── v10.0: Integrations ───────────────────────────────────────────────────────────────────────────────────────────────

export async function listIntegrations() {
  const res = await fetch(`${BASE}/integrations`, { headers: headers() });
  return res.json();
}

export async function syncIntegration(serviceName: string) {
  const res = await fetch(`${BASE}/integrations/${serviceName}/sync`, { method: "POST", headers: headers() });
  return res.json();
}

// ── v13.0: Monitoring ─────────────────────────────────────────────────────────────────────────────────────────────────

export async function getMonitorStatus() {
  const res = await fetch(`${BASE}/monitor/status`, { headers: headers() });
  return res.json();
}

export async function listAlertEvents(limit = 20) {
  const res = await fetch(`${BASE}/alerts/events?limit=${limit}`, { headers: headers() });
  return res.json();
}

export async function acknowledgeAlert(eventId: string) {
  await fetch(`${BASE}/alerts/events/${eventId}/acknowledge`, { method: "POST", headers: headers() });
}

// ── v7.0: Books ───────────────────────────────────────────────────────────────────────────────────────────────────────

export interface Book {
  id: string;
  title: string;
  author: string | null;
  category: string | null;
  tags: string[];
  ingested: boolean;
  ingestion_status: string;
  summary: string | null;
  source_ref?: string | null;
  created_at: string;
}

export interface IngestBookResponse {
  status: string;
  job_id: string;
  book_id: string;
  message?: string;
}

export async function listBooks(category?: string): Promise<Book[]> {
  const qs = category ? `?category=${category}` : "";
  const res = await fetch(`${BASE}/books${qs}`, { headers: headers() });
  return res.json();
}

export async function addBook(data: Record<string, unknown>): Promise<Book> {
  const res = await fetch(`${BASE}/books`, {
    method: "POST", headers: headers(), body: JSON.stringify(data),
  });
  return res.json();
}

export async function getBook(bookId: string): Promise<Book> {
  const res = await fetch(`${BASE}/books/${bookId}`, { headers: headers() });
  if (!res.ok) throw new Error(`Book not found: ${bookId}`);
  return res.json();
}

export async function deleteBook(bookId: string): Promise<void> {
  await fetch(`${BASE}/books/${bookId}`, { method: "DELETE", headers: headers() });
}

export async function ingestBook(bookId: string): Promise<IngestBookResponse> {
  const res = await fetch(`${BASE}/books/${bookId}/ingest`, { method: "POST", headers: headers() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Book ingestion failed" }));
    throw new Error(err.detail || `Book ingestion failed: ${res.status}`);
  }
  return res.json();
}

// ── v16.0: Agent Tasks ────────────────────────────────────────────────────────────────────────────────────────────────

export async function listAgentTasks(status?: string) {
  const qs = status ? `?status=${status}` : "";
  const res = await fetch(`${BASE}/agent-tasks${qs}`, { headers: headers() });
  return res.json();
}

export async function createAgentTask(data: Record<string, unknown>) {
  const res = await fetch(`${BASE}/agent-tasks`, {
    method: "POST", headers: headers(), body: JSON.stringify(data),
  });
  return res.json();
}

export async function cancelAgentTask(taskId: string) {
  await fetch(`${BASE}/agent-tasks/${taskId}/cancel`, { method: "POST", headers: headers() });
}

// ── v20.0: Artifacts ──────────────────────────────────────────────────────────────────────────────────────────────────

export async function listArtifacts(params?: {
  type?: string;
  session_id?: string;
  limit?: number;
  offset?: number;
}): Promise<Artifact[]> {
  const qs = new URLSearchParams();
  if (params?.type) qs.set("type", params.type);
  if (params?.session_id) qs.set("session_id", params.session_id);
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.offset) qs.set("offset", String(params.offset));

  const res = await fetch(`${BASE}/artifacts/?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list artifacts: ${res.status}`);
  return res.json();
}

export async function countArtifacts(params?: { type?: string }): Promise<number> {
  const qs = new URLSearchParams();
  if (params?.type) qs.set("type", params.type);

  const res = await fetch(`${BASE}/artifacts/count?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to count artifacts: ${res.status}`);
  const data = await res.json();
  return data.total ?? 0;
}

export async function getArtifact(id: string): Promise<Artifact> {
  const res = await fetch(`${BASE}/artifacts/${id}`, { headers: headers() });
  if (!res.ok) throw new Error(`Artifact not found: ${id}`);
  return res.json();
}

export async function createArtifact(data: {
  session_id: string;
  type: string;
  title: string;
  description?: string;
  spec?: Record<string, unknown>;
  url?: string;
  data_summary?: string;
  tags?: string[];
}): Promise<Artifact> {
  const res = await fetch(`${BASE}/artifacts/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error("Failed to create artifact");
  return res.json();
}

export async function deleteArtifact(id: string): Promise<void> {
  await fetch(`${BASE}/artifacts/${id}`, { method: "DELETE", headers: headers() });
}

// ── Ontology ───────────────────────────────────────────────────────────────────────────────────────────────────────────
// Fixed vs. the previous version: ontology/page.tsx and scenarios/page.tsx
// previously called bare fetch("/api/ontology/...") with no BASE and no
// API key — that only ever worked if the Next.js server happened to proxy
// /api to dawn-api, which nothing in next.config.mjs sets up. All ontology
// and decision calls now go through BASE + headers() like every other
// endpoint in this file.

export interface OntologyObjectType {
  object_type: string;
  source_table: string;
  source_kind: string;
  primary_key_column: string;
  properties: Record<string, { column: string; type: string; decision_relevant: boolean }>;
  default_filter: Record<string, unknown>;
  client_id: string | null;
}

export interface OntologyRelationship {
  id: string;
  from_object: string;
  to_object: string;
  relationship_name: string;
  join_definition: Record<string, unknown>;
  client_id: string | null;
}

export async function listOntologyObjects(clientId?: string): Promise<OntologyObjectType[]> {
  const qs = new URLSearchParams();
  if (clientId) qs.set("client_id", clientId);
  const res = await fetch(`${BASE}/api/ontology/objects?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list ontology objects: ${res.status}`);
  const data = await res.json();
  return data.data ?? [];
}

export async function listOntologyRelationships(clientId?: string): Promise<OntologyRelationship[]> {
  const qs = new URLSearchParams();
  if (clientId) qs.set("client_id", clientId);
  const res = await fetch(`${BASE}/api/ontology/relationships?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list ontology relationships: ${res.status}`);
  const data = await res.json();
  return data.data ?? [];
}

export async function registerOntologyObject(data: {
  object_type: string;
  source_table: string;
  primary_key_column?: string;
  properties?: Record<string, unknown>;
  source_kind?: string;
  default_filter?: Record<string, unknown>;
  client_id?: string;
}): Promise<OntologyObjectType> {
  const res = await fetch(`${BASE}/api/ontology/objects`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Failed to register object type: ${res.status}`);
  }
  const result = await res.json();
  return result.data;
}

export async function registerOntologyRelationship(data: {
  from_object: string;
  to_object: string;
  relationship_name: string;
  join_definition: Record<string, unknown>;
  client_id?: string;
}): Promise<OntologyRelationship> {
  const res = await fetch(`${BASE}/api/ontology/relationships`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Failed to register relationship: ${res.status}`);
  }
  const result = await res.json();
  return result.data;
}

export async function queryOntology(params: {
  object_type: string;
  filters?: Record<string, unknown>;
  expand?: string[];
  limit?: number;
  client_id?: string;
}): Promise<{ object: string; data: Record<string, unknown>[]; count: number; source_table: string }> {
  const res = await fetch(`${BASE}/api/ontology/query`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      object_type: params.object_type,
      filters: params.filters ?? {},
      expand: params.expand ?? [],
      limit: params.limit ?? 20,
      client_id: params.client_id,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Ontology query failed: ${res.status}`);
  }
  return res.json();
}

// ── Decision Workflows ─────────────────────────────────────────────────────────────────────────────────────────────────

export interface DecisionWorkflowSummary {
  name: string;
  description: string;
  requires_approval: boolean;
  candidate_object_type: string | null;
  input_schema: Record<string, { type: string; required?: boolean }>;
  client_id: string | null;
}

export interface ConstraintResult {
  name: string;
  passed: boolean;
  score: number | null;
  weight: number | null;
  explanation: string;
}

export interface RankedOption {
  option: Record<string, any>;
  constraint_results: ConstraintResult[];
  hard_constraints_passed: boolean;
  soft_score: number;
}

export interface DecisionRunResult {
  workflow_name: string;
  ranked_options: RankedOption[];
  recommended: { option: Record<string, any>; score: number } | null;
  requires_approval: boolean;
  explanation: string;
  decision_log_id: string | null;
  timestamp: string;
}

export async function listDecisionWorkflows(clientId?: string): Promise<DecisionWorkflowSummary[]> {
  const qs = new URLSearchParams();
  if (clientId) qs.set("client_id", clientId);
  const res = await fetch(`${BASE}/api/decision/workflows?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list workflows: ${res.status}`);
  const data = await res.json();
  return data.data ?? [];
}

export async function runDecisionWorkflow(params: {
  workflow_name: string;
  inputs?: Record<string, unknown>;
  triggered_by?: string;
  client_id?: string;
}): Promise<DecisionRunResult> {
  const res = await fetch(`${BASE}/api/decision/run`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      workflow_name: params.workflow_name,
      inputs: params.inputs ?? {},
      triggered_by: params.triggered_by ?? "user",
      client_id: params.client_id,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Workflow run failed: ${res.status}`);
  }
  return res.json();
}

export async function approveDecision(
  decisionId: string,
  data: { decision: "approved" | "rejected" | "overridden"; by: string; override_reason?: string }
): Promise<{ status: string; decision: string; id: string }> {
  const res = await fetch(`${BASE}/api/decision/${decisionId}/approve`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Approve action failed: ${res.status}`);
  }
  return res.json();
}

export async function runDecisionSimulation(params: {
  workflow_name: string;
  inputs?: Record<string, unknown>;
  mutations?: Array<{ mutation_type: string; target_id: string; property: string; new_value: unknown; label?: string }>;
  client_id?: string;
}): Promise<{
  baseline: DecisionRunResult;
  scenario: DecisionRunResult;
  diff: { recommendation_changed: boolean; baseline_recommendation: any; scenario_recommendation: any };
  mutations: Array<{ type: string; target: string; label: string }>;
}> {
  const res = await fetch(`${BASE}/api/decision/simulate`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      workflow_name: params.workflow_name,
      inputs: params.inputs ?? {},
      mutations: params.mutations ?? [],
      client_id: params.client_id,
    }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Simulation failed: ${res.status}`);
  }
  return res.json();
}

// ── Data Source Health ─────────────────────────────────────────────────────────────────────────────────────────────────

export interface DataSourceHealth {
  name: string;
  table: string;
  status: "live" | "empty" | "error" | string;
  record_count: number;
  last_sync: string | null;
  error?: string;
}

export async function getDataSourceHealth(clientId?: string): Promise<DataSourceHealth[]> {
  const qs = new URLSearchParams();
  if (clientId) qs.set("client_id", clientId);
  const res = await fetch(`${BASE}/api/admin/data-sources?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to fetch data source health: ${res.status}`);
  const data = await res.json();
  return data.sources ?? [];
}

// ── Decision Log ───────────────────────────────────────────────────────────────────────────────────────────────────────

export interface DecisionLogEntry {
  id: string;
  workflow_name: string;
  triggered_by: string;
  llm_explanation: string;
  human_decision: string | null;
  human_decision_by: string | null;
  human_decision_at: string | null;
  override_reason: string | null;
  executed: boolean;
  created_at: string;
  ranked_options: any;
  constraint_results: any;
  recommended_option: any;
  input_snapshot: any;
  data_freshness: any;
}

export async function listDecisionLog(params?: {
  workflow?: string;
  decision?: string;
  limit?: number;
  offset?: number;
}): Promise<DecisionLogEntry[]> {
  const qs = new URLSearchParams();
  if (params?.workflow) qs.set("workflow", params.workflow);
  if (params?.decision) qs.set("decision", params.decision);
  qs.set("limit", String(params?.limit ?? 50));
  if (params?.offset) qs.set("offset", String(params.offset));

  const res = await fetch(`${BASE}/api/decision/log?${qs}`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to fetch decision log: ${res.status}`);
  const data = await res.json();
  return data.data ?? [];
}

