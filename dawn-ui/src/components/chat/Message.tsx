import { Zap } from "lucide-react";
import clsx from "clsx";
import type { ChatMessage } from "@/lib/types";
import ToolCallIndicator from "./ToolCallIndicator";

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
  streamingToolCalls?: import("@/lib/types").ToolCall[];
}

export default function Message({ message, isStreaming, streamingToolCalls }: Props) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-br-sm bg-elevated border border-rim text-text-primary text-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 animate-slide-up">
      {/* DAWN avatar */}
      <div className="w-7 h-7 rounded-lg bg-dawn/10 border border-dawn/30 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Zap size={12} className="text-dawn" />
      </div>

      <div className="flex-1 min-w-0">
        {/* Tool calls */}
        {(isStreaming ? streamingToolCalls : message.tool_calls) && (
          <ToolCallIndicator
            toolCalls={(isStreaming ? streamingToolCalls : message.tool_calls) || []}
            thinking={isStreaming && (!streamingToolCalls || streamingToolCalls.length === 0)}
          />
        )}

        {/* Response content */}
        <div
          className={clsx(
            "text-sm leading-relaxed dawn-prose",
            isStreaming && "border-l-2 border-dawn/30 pl-3",
          )}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
        />

        {/* Streaming cursor */}
        {isStreaming && (
          <span className="inline-block w-1.5 h-3.5 bg-dawn/70 ml-0.5 animate-pulse rounded-sm align-middle" />
        )}

        {/* Node citations */}
        {!isStreaming && message.node_titles && message.node_titles.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {message.node_titles.map((title, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dawn/8 border border-dawn/15 text-dawn/70 text-[10px] font-mono"
              >
                <span className="w-1 h-1 rounded-full bg-dawn/50" />
                {title}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Minimal markdown renderer ──────────────────────────────────────────────────
// Full library would be better for v1.1 — this handles the common cases
function renderMarkdown(text: string): string {
  return text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`
    )
    // Inline code
    .replace(/`([^`]+)`/g, (_, code) => `<code>${escapeHtml(code)}</code>`)
    // Bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // Headers
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/^# (.+)$/gm, "<h1>$1</h1>")
    // Unordered lists
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    // Line breaks
    .replace(/\n\n/g, "</p><p>")
    .replace(/^([^<].*)$/gm, (line) =>
      line.trim() && !line.startsWith("<") ? `<p>${line}</p>` : line
    );
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
