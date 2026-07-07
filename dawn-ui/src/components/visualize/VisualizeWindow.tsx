"use client";

import { useState, useRef, useEffect, useCallback, lazy, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Send,
  RotateCcw,
  BarChart3,
  Globe2,
  Globe,
  Plus,
  Settings,
  Sparkles,
  Image,
  Table2,
  Loader2,
} from "lucide-react";
import Link from "next/link";
import { getSessionMessages, createSession } from "@/lib/api";
import { streamAgent } from "@/lib/agent-api";
import type { ChatMessage, ToolCall, SessionMessage, Artifact } from "@/lib/types";
import type { AgentChatMessage, ArtifactRef } from "@/lib/agent-types";
import Message from "@/components/chat/Message";
import clsx from "clsx";

// Lazy load ChartRenderer — vega-embed is heavy and only needed at runtime
const ChartRenderer = lazy(() => import("./ChartRenderer"));

let messageId = 0;
const nextId = () => String(++messageId);

function sessionMessageToChatMessage(sm: SessionMessage): AgentChatMessage {
  return {
    id: sm.id,
    role: sm.role,
    content: sm.content,
    tool_calls: sm.tool_calls ?? undefined,
    node_ids: sm.node_ids ?? undefined,
    node_titles: sm.node_titles ?? undefined,
    timestamp: new Date(sm.created_at),
  };
}

function notifySidebarRefresh() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("dawn:session-changed"));
  }
}

export default function VisualizeWindow() {
  const searchParams = useSearchParams();
  const sessionIdFromUrl = searchParams.get("id");

  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingToolCalls, setStreamingToolCalls] = useState<ToolCall[]>([]);
  const [thinkingState, setThinkingState] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]);
  const [showArtifactPanel, setShowArtifactPanel] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sessionId = useRef<string | undefined>(undefined);
  const prevSessionIdRef = useRef<string | null>(null);

  // Load messages when session ID changes
  useEffect(() => {
    const sid = sessionIdFromUrl;
    if (sid === prevSessionIdRef.current) return;
    prevSessionIdRef.current = sid;

    if (!sid) {
      sessionId.current = undefined;
      setMessages([]);
      setArtifacts([]);
      return;
    }

    setLoadingSession(true);
    sessionId.current = sid;

    getSessionMessages(sid)
      .then((msgs) => {
        setMessages(msgs.map(sessionMessageToChatMessage));
      })
      .catch((err) => {
        console.error("[VisualizeWindow] Failed to load messages:", err);
        setMessages([]);
      })
      .finally(() => setLoadingSession(false));
  }, [sessionIdFromUrl]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [input]);

  const buildHistory = useCallback(
    () => messages.map((m) => ({ role: m.role, content: m.content })),
    [messages]
  );

  const adoptSessionId = useCallback((newSessionId: string) => {
    if (sessionId.current === newSessionId) return;
    sessionId.current = newSessionId;
    const url = new URL(window.location.href);
    url.searchParams.set("id", newSessionId);
    window.history.replaceState({}, "", url.toString());
    prevSessionIdRef.current = newSessionId;
    notifySidebarRefresh();
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    if (!sessionId.current) {
      try {
        const session = await createSession("Visualize - " + text.slice(0, 40));
        adoptSessionId(session.id);
      } catch (err) {
        console.error("[VisualizeWindow] Failed to create session:", err);
        return;
      }
    }

    const userMsg: AgentChatMessage = {
      id: nextId(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);
    setStreamingContent("");
    setStreamingToolCalls([]);
    setThinkingState(true);

    let fullContent = "";
    let finalNodeIds: string[] = [];
    let finalNodeTitles: string[] = [];
    const toolCalls: ToolCall[] = [];
    const newArtifacts: ArtifactRef[] = [];

    try {
      // Visualize mode goes through the agent loop (not plain /chat/) because
      // producing a chart requires real tool-calling — the create_chart tool
      // builds a Vega-Lite spec, which routers/agent.py then persists as an
      // artifact and streams back as an "artifact" event.
      for await (const event of streamAgent(
        text,
        buildHistory(),
        sessionId.current,
      )) {
        switch (event.type) {
          case "thinking":
            setThinkingState(true);
            break;
          case "tool_call":
            toolCalls.push({
              name: event.name,
              args: event.args,
              result_count: 0,
            });
            setStreamingToolCalls([...toolCalls]);
            setThinkingState(false);
            break;
          case "tool_result":
            setThinkingState(false);
            break;
          case "artifact":
            newArtifacts.push({
              id: event.artifact_id,
              type: event.artifact_type as ArtifactRef["type"],
              title: event.title,
              spec: event.spec,
              url: event.url,
              created_at: new Date().toISOString(),
            });
            break;
          case "token":
            fullContent += event.content;
            setStreamingContent(fullContent);
            setThinkingState(false);
            break;
          case "warning":
            fullContent += `\n\n⚠️ ${event.content}`;
            setStreamingContent(fullContent);
            break;
          case "done":
            if (event.session_id) adoptSessionId(event.session_id);
            break;
          case "iteration_limit":
          case "error":
            fullContent = fullContent || `⚠️ ${event.content}`;
            setStreamingContent(fullContent);
            break;
        }
      }
    } catch (err) {
      console.error("[sendVisualize] error:", err);
      fullContent = "⚠️ Connection error. Is the DAWN API running?";
      setStreamingContent(fullContent);
    }

    const assistantMsg: AgentChatMessage = {
      id: nextId(),
      role: "assistant",
      content: fullContent,
      tool_calls: toolCalls,
      node_ids: finalNodeIds,
      node_titles: finalNodeTitles,
      artifacts: newArtifacts,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);
    if (newArtifacts.length > 0) {
      setArtifacts((prev) => [...prev, ...newArtifacts]);
    }
    setIsStreaming(false);
    setStreamingContent("");
    setStreamingToolCalls([]);
    setThinkingState(false);
  }, [input, isStreaming, buildHistory, adoptSessionId, webSearchEnabled]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleNewChat = async () => {
    try {
      const session = await createSession("Visualize");
      const url = new URL(window.location.href);
      url.searchParams.set("id", session.id);
      window.history.replaceState({}, "", url.toString());
      prevSessionIdRef.current = session.id;
      sessionId.current = session.id;
      setMessages([]);
      setArtifacts([]);
      notifySidebarRefresh();
    } catch (err) {
      console.error("[VisualizeWindow] Failed to create session:", err);
    }
  };

  return (
    <div className="flex h-full">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 space-y-4 sm:space-y-5">
          {loadingSession ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-text-muted text-sm">Loading conversation...</div>
            </div>
          ) : messages.length === 0 && !isStreaming ? (
            <EmptyState webSearchEnabled={webSearchEnabled} />
          ) : (
            <>
              {messages.map((msg) => (
                <div key={msg.id}>
                  <Message message={msg} />

                  {/* Render charts embedded in assistant messages */}
                  {msg.role === "assistant" && (
                    <ChartsFromContent content={msg.content} />
                  )}
                </div>
              ))}

              {/* Streaming message */}
              {isStreaming && (
                <div>
                  <Message
                    message={{
                      id: "streaming",
                      role: "assistant",
                      content: streamingContent,
                      timestamp: new Date(),
                    }}
                    isStreaming
                    streamingToolCalls={!thinkingState ? streamingToolCalls : []}
                  />
                  {/* Live chart rendering while streaming */}
                  {streamingContent && (
                    <ChartsFromContent content={streamingContent} />
                  )}
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input bar */}
        <div className="border-t border-rim px-3 sm:px-4 pb-3 sm:pb-4 pt-2 sm:pt-3">
          {/* Controls */}
          <div className="flex items-center justify-between mb-2 sm:mb-3">
            <div className="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-elevated/60 border border-rim">
              <div className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-3 py-1.5 rounded-md bg-dawn/90 text-white shadow-soft text-xs font-medium">
                <BarChart3 size={12} />
                <span className="hidden xs:inline">Visualize</span>
              </div>
            </div>

            <div className="flex items-center gap-1">
              {/* Web search toggle */}
              <button
                onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                disabled={isStreaming}
                className={clsx(
                  "flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg transition-all text-xs font-medium",
                  webSearchEnabled
                    ? "bg-dawn/15 text-dawn border border-dawn/30"
                    : "text-text-muted hover:text-text-secondary hover:bg-elevated/60 border border-transparent"
                )}
                title={webSearchEnabled ? "Web search ON" : "Web search OFF"}
              >
                {webSearchEnabled ? <Globe size={12} /> : <Globe2 size={12} />}
                <span className="hidden xs:inline">{webSearchEnabled ? "Web ON" : "Web"}</span>
              </button>

              {/* Artifacts panel toggle */}
              {artifacts.length > 0 && (
                <button
                  onClick={() => setShowArtifactPanel(!showArtifactPanel)}
                  className={clsx(
                    "flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg transition-all text-xs",
                    showArtifactPanel
                      ? "bg-dawn/15 text-dawn border border-dawn/30"
                      : "text-text-muted hover:text-text-secondary hover:bg-elevated/60 border border-transparent"
                  )}
                >
                  <Image size={12} />
                  <span className="hidden xs:inline">{artifacts.length}</span>
                </button>
              )}

              <button
                onClick={handleNewChat}
                className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
                title="New session"
              >
                <Plus size={12} />
                <span className="hidden xs:inline">New</span>
              </button>
              {messages.length > 0 && (
                <button
                  onClick={() => { setMessages([]); setArtifacts([]); }}
                  className="flex items-center gap-1 sm:gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
                >
                  <RotateCcw size={12} />
                  <span className="hidden xs:inline">Clear</span>
                </button>
              )}
              <Link
                href="/settings"
                className="flex items-center gap-1.5 px-2 sm:px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
              >
                <Settings size={12} />
              </Link>
            </div>
          </div>

          <div className="flex items-end gap-2 bg-surface border border-rim rounded-xl px-3 sm:px-4 py-2 sm:py-2.5 input-glow transition-all shadow-soft">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask DAWN to visualize something..."
              rows={1}
              disabled={isStreaming}
              className="flex-1 bg-transparent text-text-primary text-sm placeholder:text-text-muted resize-none outline-none leading-relaxed py-1 max-h-40 disabled:opacity-50"
            />
            <button
              onClick={send}
              disabled={!input.trim() || isStreaming}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-dawn/90 text-white hover:bg-dawn disabled:opacity-30 disabled:cursor-not-allowed transition-all flex-shrink-0"
            >
              <Send size={13} />
            </button>
          </div>
          <p className="text-text-muted text-2xs mt-1.5 px-1 hidden sm:block">
            Shift+Enter for new line · DAWN can generate charts, tables, and visualizations from your data
            {webSearchEnabled && " · Web search is ON"}
          </p>
        </div>
      </div>

      {/* Artifacts side panel */}
      {showArtifactPanel && artifacts.length > 0 && (
        <div className="w-72 border-l border-rim bg-surface/80 backdrop-blur-sm overflow-y-auto flex-shrink-0 hidden md:block">
          <div className="p-3">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-medium text-text-primary flex items-center gap-1.5">
                <Image size={12} className="text-dawn" />
                Artifacts
              </h3>
              <button
                onClick={() => setShowArtifactPanel(false)}
                className="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
              >
                <span className="text-xs">✕</span>
              </button>
            </div>
            <div className="space-y-2">
              {artifacts.map((art, i) => (
                <div
                  key={art.id || i}
                  className="p-2 rounded-lg bg-elevated/40 border border-rim text-xs"
                >
                  <div className="flex items-center gap-1.5 mb-1">
                    {art.type === "chart" ? (
                      <BarChart3 size={10} className="text-dawn" />
                    ) : art.type === "table" ? (
                      <Table2 size={10} className="text-dawn" />
                    ) : (
                      <Image size={10} className="text-dawn" />
                    )}
                    <span className="text-text-primary font-medium truncate">{art.title}</span>
                  </div>
                  <span className="text-text-muted text-2xs">{art.type}</span>
                </div>
              ))}
            </div>
            <Link
              href="/artifacts"
              className="mt-3 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
            >
              <Sparkles size={11} />
              View all artifacts
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

/** Extracts and renders Vega-Lite charts from message content */
function ChartsFromContent({ content }: { content: string }) {
  const charts: { spec: Record<string, unknown>; title: string }[] = [];
  const regex = /```vega-lite\n([\s\S]*?)```/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    try {
      const spec = JSON.parse(match[1]);
      charts.push({ spec, title: spec.title || "Chart" });
    } catch {
      // skip invalid JSON
    }
  }

  if (charts.length === 0) return null;

  return (
    <div className="ml-0 sm:ml-12 mt-3 space-y-3">
      {charts.map((chart, i) => (
        <Suspense
          key={i}
          fallback={
            <div className="flex items-center justify-center py-8 rounded-xl border border-rim bg-surface/50">
              <Loader2 size={16} className="text-dawn animate-spin" />
            </div>
          }
        >
          <ChartRenderer
            spec={chart.spec}
            title={chart.title}
          />
        </Suspense>
      ))}
    </div>
  );
}

function EmptyState({ webSearchEnabled }: { webSearchEnabled: boolean }) {
  const suggestions = [
    "Show me a bar chart of node types in the knowledge graph",
    "Visualize the distribution of edge relations",
    "Chart the growth of my knowledge base over time",
    "Create a pie chart of node statuses (active, draft, stale)",
    "Compare the number of concepts vs entities in the graph",
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 sm:gap-8 py-8 sm:py-16 px-3 sm:px-0">
      <div className="text-center">
        <div className="relative mx-auto mb-4 sm:mb-5">
          <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-2xl bg-gradient-to-br from-dawn/15 to-ember/10 border border-dawn/25 flex items-center justify-center shadow-dawn">
            <BarChart3 size={22} className="text-dawn" strokeWidth={1.5} />
          </div>
          <div className="absolute -bottom-1 -right-1 w-4 h-4 sm:w-5 sm:h-5 rounded-full bg-surface border border-rim flex items-center justify-center">
            <span className="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-success" />
          </div>
        </div>
        <h2 className="text-text-primary font-semibold text-lg sm:text-xl tracking-tight">
          Visualize
        </h2>
        <p className="text-text-muted text-sm mt-1">
          Data visualization mode
        </p>
        <p className="text-text-muted text-2xs mt-1.5 font-mono">
          Ask DAWN to chart, graph, and visualize your data
        </p>
        {webSearchEnabled && (
          <div className="mt-2 inline-flex items-center gap-1 px-2 py-1 rounded-full bg-dawn/10 border border-dawn/20 text-dawn text-2xs">
            <Globe size={10} />
            Web search enabled
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 w-full max-w-lg">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => {
              const ta = document.querySelector("textarea");
              if (ta) {
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                  window.HTMLTextAreaElement.prototype,
                  "value"
                )?.set;
                nativeInputValueSetter?.call(ta, s);
                ta.dispatchEvent(new Event("input", { bubbles: true }));
              }
            }}
            className="text-left px-3 sm:px-4 py-2.5 sm:py-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 text-text-secondary text-sm transition-all hover:text-text-primary hover:shadow-soft hover:bg-surface-hover"
          >
            {s}
          </button>
        ))}
      </div>

      <div className="w-24 sm:w-32 dawn-line opacity-30" />
    </div>
  );
}
