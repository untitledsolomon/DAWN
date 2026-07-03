// ── Additions to src/lib/api.ts ─────────────────────────────────────────────
// Add this import at the top of api.ts:
//   import type { AgentSSEEvent } from "./agent-types";
// Then add the function below anywhere in the file (e.g. right after streamChat).

import type { AgentSSEEvent } from "./agent-types";

// Self-contained on purpose — mirrors api.ts's BASE/headers rather than
// importing them, since api.ts doesn't export them (they're module-private
// consts there). Keeping this file standalone avoids editing api.ts at all.
const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "X-API-Key": KEY,
});

export async function* streamAgent(
  message: string,
  history: { role: string; content: string }[],
  maxIterations?: number,
): AsyncGenerator<AgentSSEEvent> {
  const res = await fetch(`${BASE}/agent/`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      message,
      history,
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
          // Malformed SSE line — skip, same handling as streamChat
        }
      }
    }
  }
}