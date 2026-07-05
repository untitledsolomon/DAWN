import type { DawnNode, Tag, IngestionLog, SSEEvent, ChatSession, SessionMessage, AppSettings, NotificationPrefs, AgentLogEntry } from "./types";
import type { AgentSSEEvent } from "./agent-types";

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

// ── Nodes ──────────────────────────────────────────────────────────────────

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

// ── Tags ───────────────────────────────────────────────────────────────────

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

// ── Edges ──────────────────────────────────────────────────────────────────

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

// ── Search ─────────────────────────────────────────────────────────────────

export async function searchNodes(q: string, limit = 10): Promise<DawnNode[]> {
  const res = await fetch(`${BASE}/search/?q=${encodeURIComponent(q)}&limit=${limit}`, { headers: headers() });
  return res.json();
}

export async function traverseNode(nodeId: string, depth = 2) {
  const res = await fetch(`${BASE}/search/traverse/${nodeId}?depth=${depth}`, { headers: headers() });
  return res.json();
}

// ── Chat (streaming) ───────────────────────────────────────────────────────

export async function* streamChat(
  message: string,
  history: { role: string; content: string }[],
  sessionId?: string,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/chat/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ message, history, session_id: sessionId }),
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

// ── Chat Sessions ──────────────────────────────────────────────────────────

export async function listSessions(): Promise<ChatSession[]> {
  const res = await fetch(`${BASE}/chat/sessions`, { headers: headers() });
  if (!res.ok) throw new Error(`Failed to list sessions: ${res.status}`);
  return res.json();
}

export async function createSession(title = "New Chat"): Promise<ChatSession> {
  const res = await fetch(`${BASE}/chat/sessions`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ title }),
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

// ── Settings ───────────────────────────────────────────────────────────────

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

// ── Notifications ──────────────────────────────────────────────────────────

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

// ── Agent Logs ─────────────────────────────────────────────────────────────

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

// ── Ingestion ──────────────────────────────────────────────────────────────

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

export async function ingestFile(file: File, title: string, tags: string[] = []): Promise<{ status: string; title: string; file_type: string; word_count: number; sections: number; filename: string }> {
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

export async function getIngestionLog(): Promise<IngestionLog[]> {
  const res = await fetch(`${BASE}/ingest/log`, { headers: headers() });
  return res.json();
}

// ── Health ─────────────────────────────────────────────────────────────────

export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.json();
  } catch {
    return { status: "offline" };
  }
}

// ── v3.0: SSH Hosts ────────────────────────────────────────────────────────

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

// ── v5.0: OSINT ────────────────────────────────────────────────────────────

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

// ── v6.0: Pentesting ───────────────────────────────────────────────────────

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

// ── v10.0: Integrations ────────────────────────────────────────────────────

export async function listIntegrations() {
  const res = await fetch(`${BASE}/integrations`, { headers: headers() });
  return res.json();
}

export async function syncIntegration(serviceName: string) {
  const res = await fetch(`${BASE}/integrations/${serviceName}/sync`, { method: "POST", headers: headers() });
  return res.json();
}

// ── v13.0: Monitoring ──────────────────────────────────────────────────────

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

// ── v7.0: Books ────────────────────────────────────────────────────────────

export async function listBooks(category?: string) {
  const qs = category ? `?category=${category}` : "";
  const res = await fetch(`${BASE}/books${qs}`, { headers: headers() });
  return res.json();
}

export async function addBook(data: Record<string, unknown>) {
  const res = await fetch(`${BASE}/books`, {
    method: "POST", headers: headers(), body: JSON.stringify(data),
  });
  return res.json();
}

export async function ingestBook(bookId: string) {
  const res = await fetch(`${BASE}/books/${bookId}/ingest`, { method: "POST", headers: headers() });
  return res.json();
}

// ── v16.0: Agent Tasks ─────────────────────────────────────────────────────

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
