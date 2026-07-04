"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "next/navigation";
import {
  Send,
  RotateCcw,
  Bot,
  MessageSquare,
  Sparkles,
  Zap,
  Plus,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { streamChat, getSessionMessages, createSession } from "@/lib/api";
import { streamAgent } from "@/lib/agent-api";
import type { ChatMessage, ToolCall, SessionMessage } from "@/lib/types";
import type {
  AgentChatMessage,
  AgentTraceEntry,
  ChatMode,
} from "@/lib/agent-types";
import Message from "./Message";
import AgentTraceIndicator, {
  AgentWarningBanner,
} from "./AgentTraceIndicator";

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

/** Dispatch a custom event so the Sidebar knows to refresh its session list */
function notifySidebarRefresh() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("dawn:session-changed"));
  }
}

export default function ChatWindow() {
  const searchParams = useSearchParams();
  const sessionIdFromUrl = searchParams.get("id");

  const [mode, setMode] = useState<ChatMode>("chat");
  const [messages, setMessages] = useState<AgentChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingToolCalls, setStreamingToolCalls] = useState<
    ToolCall[]
  >([]);
  const [streamingTrace, setStreamingTrace] = useState<
    AgentTraceEntry[]
  >([]);
  const [streamingWarning, setStreamingWarning] = useState<
    string | null
  >(null);
  const [thinkingState, setThinkingState] = useState(false);
  const [thinkingLabel, setThinkingLabel] = useState("");
  const [loadingSession, setLoadingSession] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sessionId = useRef<string | undefined>(undefined);
  const prevSessionIdRef = useRef<string | null>(null);

  // ── Load messages when session ID changes ──────────────────────────
  useEffect(() => {
    const sid = sessionIdFromUrl;

    // If same session, don't reload
    if (sid === prevSessionIdRef.current) return;
    prevSessionIdRef.current = sid;

    if (!sid) {
      // No session — start fresh
      sessionId.current = undefined;
      setMessages([]);
      return;
    }

    // Load messages for this session
    setLoadingSession(true);
    sessionId.current = sid;

    getSessionMessages(sid)
      .then((msgs) => {
        setMessages(msgs.map(sessionMessageToChatMessage));
      })
      .catch((err) => {
        console.error("[ChatWindow] Failed to load messages:", err);
        setMessages([]);
      })
      .finally(() => {
        setLoadingSession(false);
      });
  }, [sessionIdFromUrl]);

  // Auto-scroll to bottom
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
    () =>
      messages.map((m) => ({ role: m.role, content: m.content })),
    [messages],
  );

  /** Shared by both sendChat and sendAgent: adopt a session_id the backend
   * created/confirmed, sync it into the URL, and tell the sidebar to refresh
   * so the new/renamed session shows up in the list. */
  const adoptSessionId = useCallback((newSessionId: string) => {
    if (sessionId.current === newSessionId) return;
    sessionId.current = newSessionId;
    const url = new URL(window.location.href);
    url.searchParams.set("id", newSessionId);
    window.history.replaceState({}, "", url.toString());
    prevSessionIdRef.current = newSessionId;
    notifySidebarRefresh();
  }, []);

  const sendChat = useCallback(
    async (text: string) => {
      let fullContent = "";
      let finalNodeIds: string[] = [];
      let finalNodeTitles: string[] = [];
      const toolCalls: ToolCall[] = [];

      try {
        for await (const event of streamChat(
          text,
          buildHistory(),
          sessionId.current,
        )) {
          switch (event.type) {
            case "thinking":
              setThinkingState(true);
              break;
            case "tool":
              toolCalls.push({
                name: event.name,
                args: event.args,
                result_count: event.result_count,
              });
              setStreamingToolCalls([...toolCalls]);
              setThinkingState(false);
              break;
            case "context":
              finalNodeIds = event.node_ids;
              finalNodeTitles = event.node_titles;
              break;
            case "token":
              fullContent += event.content;
              setStreamingContent(fullContent);
              setThinkingState(false);
              break;
            case "done":
              finalNodeIds = event.node_ids;
              finalNodeTitles = event.node_titles;
              // Capture session_id from backend if provided
              if (event.session_id) {
                adoptSessionId(event.session_id);
              }
              break;
            case "error":
              fullContent = `⚠️ Error: ${event.message}`;
              setStreamingContent(fullContent);
              break;
          }
        }
      } catch (err) {
        console.error("[sendChat] error:", err);
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
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    },
    [buildHistory, adoptSessionId],
  );

  const sendAgent = useCallback(
    async (text: string) => {
      let fullContent = "";
      const trace: AgentTraceEntry[] = [];
      let warning: string | undefined;

      try {
        for await (const event of streamAgent(
          text,
          buildHistory(),
          sessionId.current,
        )) {
          switch (event.type) {
            case "thinking":
              setThinkingLabel(event.content);
              setThinkingState(true);
              break;

            case "tool_call":
              trace.push({
                call: { name: event.name, args: event.args },
              });
              setStreamingTrace([...trace]);
              setThinkingState(false);
              break;

            case "tool_result": {
              const idx = [...trace]
                .reverse()
                .findIndex(
                  (t) => t.call.name === event.name && !t.result,
                );
              if (idx !== -1) {
                const realIdx = trace.length - 1 - idx;
                trace[realIdx] = {
                  ...trace[realIdx],
                  result: {
                    name: event.name,
                    success: event.success,
                    output: event.output,
                    error: event.error,
                  },
                };
                setStreamingTrace([...trace]);
              }
              break;
            }

            case "warning":
              warning = event.content;
              setStreamingWarning(event.content);
              break;

            case "token":
              fullContent += event.content;
              setStreamingContent(fullContent);
              setThinkingState(false);
              break;

            case "done":
              fullContent = event.content;
              // Capture session_id from backend, same as sendChat — this is
              // what makes Agent mode sessions persist and get titled.
              if (event.session_id) {
                adoptSessionId(event.session_id);
              }
              break;

            case "iteration_limit":
              fullContent =
                fullContent || `⚠️ ${event.content}`;
              break;

            case "error":
              fullContent = `⚠️ Error: ${event.content}`;
              setStreamingContent(fullContent);
              break;
          }
        }
      } catch (err) {
        console.error("[sendAgent] error:", err);
        fullContent =
          "⚠️ Connection error. Is the DAWN API running?";
        setStreamingContent(fullContent);
      }

      const assistantMsg: AgentChatMessage = {
        id: nextId(),
        role: "assistant",
        content: fullContent,
        trace,
        warning,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    },
    [buildHistory, adoptSessionId],
  );

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    // If no session exists yet, create one
    if (!sessionId.current) {
      try {
        const session = await createSession();
        adoptSessionId(session.id);
      } catch (err) {
        console.error("[ChatWindow] Failed to create session:", err);
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
    setStreamingTrace([]);
    setStreamingWarning(null);
    setThinkingState(true);
    setThinkingLabel("");

    if (mode === "agent") {
      await sendAgent(text);
    } else {
      await sendChat(text);
    }

    setIsStreaming(false);
    setStreamingContent("");
    setStreamingToolCalls([]);
    setStreamingTrace([]);
    setStreamingWarning(null);
    setThinkingState(false);
  }, [input, isStreaming, mode, sendAgent, sendChat, adoptSessionId]);

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLTextAreaElement>,
  ) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleNewChat = async () => {
    try {
      const session = await createSession();
      const url = new URL(window.location.href);
      url.searchParams.set("id", session.id);
      window.history.replaceState({}, "", url.toString());
      prevSessionIdRef.current = session.id;
      sessionId.current = session.id;
      setMessages([]);
      notifySidebarRefresh();
    } catch (err) {
      console.error("[ChatWindow] Failed to create session:", err);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {loadingSession ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-text-muted text-sm">Loading conversation...</div>
          </div>
        ) : messages.length === 0 && !isStreaming ? (
          <EmptyState mode={mode} />
        ) : (
          <>
            {messages.map((msg) => (
              <div key={msg.id}>
                {msg.trace && msg.trace.length > 0 && (
                  <div className="ml-12 mb-1">
                    <AgentTraceIndicator trace={msg.trace} />
                  </div>
                )}
                {msg.warning && (
                  <div className="ml-12 mb-1">
                    <AgentWarningBanner warning={msg.warning} />
                  </div>
                )}
                <Message message={msg} />
              </div>
            ))}

            {/* Streaming message */}
            {isStreaming && (
              <div>
                {mode === "agent" && (
                  <div className="ml-12 mb-1">
                    <AgentTraceIndicator
                      trace={streamingTrace}
                      thinking={thinkingState}
                      thinkingLabel={thinkingLabel}
                    />
                    {streamingWarning && (
                      <AgentWarningBanner warning={streamingWarning} />
                    )}
                  </div>
                )}
                <Message
                  message={{
                    id: "streaming",
                    role: "assistant",
                    content: streamingContent,
                    timestamp: new Date(),
                  }}
                  isStreaming
                  streamingToolCalls={
                    mode === "chat" && !thinkingState
                      ? streamingToolCalls
                      : []
                  }
                />
              </div>
            )}
          </>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-rim px-4 pb-4 pt-3">
        {/* Mode toggle + actions */}
        <div className="flex items-center justify-between mb-3">
          <div className="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-elevated/60 border border-rim">
            <button
              onClick={() => !isStreaming && setMode("chat")}
              disabled={isStreaming}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all disabled:opacity-50 ${
                mode === "chat"
                  ? "bg-dawn/90 text-white shadow-soft"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <MessageSquare size={12} />
              Chat
            </button>
            <button
              onClick={() => !isStreaming && setMode("agent")}
              disabled={isStreaming}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all disabled:opacity-50 ${
                mode === "agent"
                  ? "bg-dawn/90 text-white shadow-soft"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <Bot size={12} />
              Agent
            </button>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={handleNewChat}
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
              title="New chat"
            >
              <Plus size={12} />
              New
            </button>
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
              >
                <RotateCcw size={12} />
                Clear
              </button>
            )}
            <Link
              href="/settings"
              className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all text-xs"
            >
              <Settings size={12} />
            </Link>
          </div>
        </div>

        <div className="flex items-end gap-2 bg-surface border border-rim rounded-xl px-4 py-2.5 input-glow transition-all shadow-soft">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              mode === "agent"
                ? "Ask DAWN to do something..."
                : "Ask DAWN anything..."
            }
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
        <p className="text-text-muted text-2xs mt-1.5 px-1">
          {mode === "agent"
            ? "Shift+Enter for new line · Agent mode can read/write files, use git, and search the web"
            : "Shift+Enter for new line · DAWN searches your knowledge graph before answering"}
        </p>
      </div>
    </div>
  );
}

function EmptyState({ mode }: { mode: ChatMode }) {
  const chatSuggestions = [
    "What's the current status of the Sentinel trading bot?",
    "Explain how Axis handles Uganda PAYE compliance",
    "What are the modules in Regent CRM?",
    "Summarise the EconSim architecture",
  ];

  const agentSuggestions = [
    "List the files in the sandbox",
    "Clone a small test repo and show me its structure",
    "Search the web for the latest DeepSeek model release",
    "Write a short README.md to the sandbox",
  ];

  const suggestions =
    mode === "agent" ? agentSuggestions : chatSuggestions;

  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 py-16">
      <div className="text-center">
        {/* Logo mark — larger, more polished */}
        <div className="relative mx-auto mb-5">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-dawn/15 to-ember/10 border border-dawn/25 flex items-center justify-center shadow-dawn">
            <Zap size={26} className="text-dawn" strokeWidth={1.5} />
          </div>
          <div className="absolute -bottom-1 -right-1 w-5 h-5 rounded-full bg-surface border border-rim flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-success" />
          </div>
        </div>
        <h2 className="text-text-primary font-semibold text-xl tracking-tight">
          DAWN
        </h2>
        <p className="text-text-muted text-sm mt-1">
          {mode === "agent"
            ? "Agent mode — tools enabled"
            : "Digital AI Working Network"}
        </p>
        <p className="text-text-muted text-2xs mt-1.5 font-mono">
          Regent Knowledge Layer · Kampala
        </p>
      </div>

      {/* Suggestion grid */}
      <div className="grid grid-cols-1 gap-2 w-full max-w-lg">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => {
              const ta = document.querySelector("textarea");
              if (ta) {
                const nativeInputValueSetter =
                  Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype,
                    "value",
                  )?.set;
                nativeInputValueSetter?.call(ta, s);
                ta.dispatchEvent(
                  new Event("input", { bubbles: true }),
                );
              }
            }}
            className="text-left px-4 py-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 text-text-secondary text-sm transition-all hover:text-text-primary hover:shadow-soft hover:bg-surface-hover"
          >
            {s}
          </button>
        ))}
      </div>

      {/* Horizon decorative line */}
      <div className="w-32 dawn-line opacity-30" />
    </div>
  );
}
