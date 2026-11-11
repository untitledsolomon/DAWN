import { User, Zap } from "lucide-react";
import clsx from "clsx";
import type { ChatMessage } from "@/lib/types";
import type { AgentChatMessage } from "@/lib/agent-types";
import ToolCallView from "./ToolCallView";
import ArtifactBody from "@/components/canvas/ArtifactBody";
import { renderMarkdown } from "@/lib/ui/markdown";

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

  // Agent-mode executed tools (real results), for completed messages.
  const trace =
    "trace" in message ? (message as AgentChatMessage).trace : undefined;

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
        {/* Tool calls — rich, collapsible view */}
        <ToolCallView
          toolCalls={
            (isStreaming ? streamingToolCalls : message.tool_calls) || []
          }
          trace={trace}
          thinking={
            isStreaming &&
            (!streamingToolCalls || streamingToolCalls.length === 0) &&
            !trace?.length
          }
        />

        {/* Response content — safe markdown → React (no dangerouslySetInnerHTML) */}
        <div
          className={clsx(
            "text-sm leading-relaxed dawn-prose",
            isStreaming && "border-l-2 border-dawn/30 pl-3",
          )}
        >
          {renderMarkdown(message.content)}
        </div>

        {/* Streaming cursor */}
        {isStreaming && (
          <span className="inline-block w-1.5 h-4 bg-dawn/70 ml-0.5 animate-pulse rounded-sm align-middle" />
        )}

        {/* Artifacts (charts, tables, images, files, explainers) inline */}
        {artifacts && artifacts.length > 0 && (
          <div className="mt-4 space-y-4">
            {artifacts.map((artifact) => (
              <ArtifactBody key={artifact.id} artifact={artifact} />
            ))}
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

// Markdown rendering lives in lib/ui/markdown.tsx (shared, escaped, no
// dangerouslySetInnerHTML).
