import { Sparkles, User, Zap } from "lucide-react";
import clsx from "clsx";
import type { ChatMessage } from "@/lib/types";
import type { AgentChatMessage } from "@/lib/agent-types";
import ToolCallIndicator from "./ToolCallIndicator";
import ChartRenderer from "../visualize/ChartRenderer";

interface Props {
  message: ChatMessage | AgentChatMessage;
  isStreaming?: boolean;
  streamingToolCalls?: import("@/lib/types").ToolCall[];
}

export default function Message({
  message,
  isStreaming,
  streamingToolCalls,
}: Props) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="max-w-[75%] flex items-start gap-3">
          <div className="flex-1 px-4 py-3 rounded-2xl rounded-br-sm bg-dawn/8 border border-dawn/15 text-text-primary text-sm leading-relaxed">
            {message.content}
          </div>
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-text-primary/5 to-text-primary/10 border border-rim flex items-center justify-center flex-shrink-0 mt-0.5 shadow-soft">
            <User size={13} className="text-text-secondary" />
          </div>
        </div>
      </div>
    );
  }

  // Check if this message has artifacts (from agent mode)
  const artifacts = "artifacts" in message ? (message as AgentChatMessage).artifacts : undefined;

  return (
    <div className="flex gap-3 animate-slide-up group">
      {/* DAWN avatar */}
      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-dawn/15 to-ember/10 border border-dawn/25 flex items-center justify-center flex-shrink-0 mt-0.5 shadow-dawn">
        <Zap size={14} className="text-dawn" />
      </div>

      <div className="flex-1 min-w-0 pt-0.5">
        {/* Tool calls */}
        {(isStreaming ? streamingToolCalls : message.tool_calls) && (
          <ToolCallIndicator
            toolCalls={
              (isStreaming
                ? streamingToolCalls
                : message.tool_calls) || []
            }
            thinking={
              isStreaming &&
              (!streamingToolCalls ||
                streamingToolCalls.length === 0)
            }
          />
        )}

        {/* Response content */}
        <div
          className={clsx(
            "text-sm leading-relaxed dawn-prose",
            isStreaming && "border-l-2 border-dawn/30 pl-3",
          )}
          dangerouslySetInnerHTML={{
            __html: renderMarkdown(message.content),
          }}
        />

        {/* Streaming cursor */}
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 bg-dawn/70 ml-0.5 animate-pulse rounded-sm align-middle" />
        )}

        {/* Artifacts (charts, tables, images) */}
        {artifacts && artifacts.length > 0 && (
          <div className="mt-4 space-y-4">
            {artifacts.map((artifact) => {
              if (artifact.type === "chart" && artifact.spec) {
                return (
                  <ChartRenderer
                    key={artifact.id}
                    spec={artifact.spec}
                    title={artifact.title}
                  />
                );
              }
              // Future: handle table, image, file types here
              return null;
            })}
          </div>
        )}

        {/* Node citations */}
        {!isStreaming &&
          message.node_titles &&
          message.node_titles.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {message.node_titles.map((title, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-dawn/8 border border-dawn/15 text-dawn/70 text-2xs font-mono"
                >
                  <span className="w-1 h-1 rounded-full bg-dawn/50" />
                  {title}
                </span>
              ))}
            </div>
          )}

        {/* Timestamp — visible on hover */}
        {!isStreaming && (
          <p className="text-text-muted text-2xs mt-1 opacity-0 group-hover:opacity-100 transition-opacity font-mono">
            {message.timestamp.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        )}
      </div>
    </div>
  );
}

// ── Minimal markdown renderer ──────────────────────────────────────────────
function renderMarkdown(text: string): string {
  return text
    // Code blocks
    .replace(
      /```(\w*)\n([\s\S]*?)```/g,
      (_, lang, code) =>
        `<pre><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`,
    )
    // Inline code
    .replace(
      /`([^`]+)`/g,
      (_, code) => `<code>${escapeHtml(code)}</code>`,
    )
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
      line.trim() && !line.startsWith("<") ? `<p>${line}</p>` : line,
    );
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
