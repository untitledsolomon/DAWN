import type { AgentSSEEvent } from "./agent-types";

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

export async function* streamAgent(
  message: string,
  history: { role: string; content: string }[],
  sessionId?: string,
  maxIterations?: number,
): AsyncGenerator<AgentSSEEvent> {
  const res = await fetch(`${BASE}/agent/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      message,
      history,
      ...(sessionId ? { session_id: sessionId } : {}),
      ...(maxIterations ? { max_iterations: maxIterations } : {}),
    }),
  });

  if (!res.ok || !res.body) {
    yield { type: "error", content: `API error: ${res.status}` };
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
          const event = JSON.parse(line.slice(6)) as AgentSSEEvent;
          yield event;
        } catch {
          // Malformed SSE line — skip
        }
      }
    }
  }
}
