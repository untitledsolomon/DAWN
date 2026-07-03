import type { DawnNode, Tag, IngestionLog, SSEEvent } from "./types";
import type { AgentSSEEvent } from "./agent-types";

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "X-API-Key": KEY,
});

// ── Nodes ─────────────────────────────────────────────────────────────────────

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
  const res = await fetch(`${BASE}/nodes/${id}/approve`, {
    method: "POST",
    headers: headers(),
  });
  return res.json();
}

export async function rejectNode(id: string) {
  const res = await fetch(`${BASE}/nodes/${id}/reject`, {
    method: "POST",
    headers: headers(),
  });
  return res.json();
}

export async function getPendingNodes(): Promise<DawnNode[]> {
  const res = await fetch(`${BASE}/nodes/memory/pending`, { headers: headers() });
  return res.json();
}

// ── Tags ──────────────────────────────────────────────────────────────────────

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

// ── Edges ─────────────────────────────────────────────────────────────────────

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

// ── Search ────────────────────────────────────────────────────────────────────

export async function searchNodes(q: string, limit = 10): Promise<DawnNode[]> {
  const res = await fetch(`${BASE}/search/?q=${encodeURIComponent(q)}&limit=${limit}`, {
    headers: headers(),
  });
  return res.json();
}

export async function traverseNode(nodeId: string, depth = 2) {
  const res = await fetch(`${BASE}/search/traverse/${nodeId}?depth=${depth}`, {
    headers: headers(),
  });
  return res.json();
}

// ── Chat (streaming) ──────────────────────────────────────────────────────────

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

// ── Ingestion ─────────────────────────────────────────────────────────────────

export async function ingestRepo(repoPath: string, repoName: string, tags: string[] = []) {
  const res = await fetch(`${BASE}/ingest/repo`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ repo_path: repoPath, repo_name: repoName, tags }),
  });
  return res.json();
}

export async function ingestDocument(
  title: string,
  content: string,
  sourceRef = "",
  tags: string[] = [],
) {
  const res = await fetch(`${BASE}/ingest/document`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ title, content, source_ref: sourceRef, tags }),
  });
  return res.json();
}

export async function ingestFile(
  file: File,
  title: string,
  tags: string[] = [],
): Promise<{ status: string; title: string; file_type: string; word_count: number; sections: number; filename: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("tags", tags.join(","));

  const res = await fetch(`${BASE}/ingest/file`, {
    method: "POST",
    headers: { "X-API-Key": KEY },
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

// ── Health ────────────────────────────────────────────────────────────────────

export async function checkHealth() {
  try {
    const res = await fetch(`${BASE}/health`);
    return res.json();
  } catch {
    return { status: "offline" };
  }
}
