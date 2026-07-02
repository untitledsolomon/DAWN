"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, RotateCcw } from "lucide-react";
import { streamChat } from "@/lib/api";
import type { ChatMessage, ToolCall } from "@/lib/types";
import Message from "./Message";

let messageId = 0;
const nextId = () => String(++messageId);

export default function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingToolCalls, setStreamingToolCalls] = useState<ToolCall[]>([]);
  const [thinkingState, setThinkingState] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sessionId = useRef(crypto.randomUUID());

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

  const buildHistory = useCallback(() =>
    messages.map((m) => ({ role: m.role, content: m.content })),
  [messages]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || isStreaming) return;

    // Add user message
    const userMsg: ChatMessage = {
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

    try {
      for await (const event of streamChat(text, buildHistory(), sessionId.current)) {
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
            break;

          case "error":
            fullContent = `⚠️ Error: ${event.message}`;
            setStreamingContent(fullContent);
            break;
        }
      }
    } catch (err) {
      fullContent = `⚠️ Connection error. Is the DAWN API running?`;
      setStreamingContent(fullContent);
    }

    // Finalise assistant message
    const assistantMsg: ChatMessage = {
      id: nextId(),
      role: "assistant",
      content: fullContent,
      tool_calls: toolCalls,
      node_ids: finalNodeIds,
      node_titles: finalNodeTitles,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setIsStreaming(false);
    setStreamingContent("");
    setStreamingToolCalls([]);
    setThinkingState(false);
  }, [input, isStreaming, buildHistory]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 && !isStreaming && (
          <EmptyState />
        )}

        {messages.map((msg) => (
          <Message key={msg.id} message={msg} />
        ))}

        {/* Streaming message */}
        {isStreaming && (
          <Message
            message={{
              id: "streaming",
              role: "assistant",
              content: streamingContent,
              timestamp: new Date(),
            }}
            isStreaming
            streamingToolCalls={thinkingState ? [] : streamingToolCalls}
          />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-rim px-4 py-3">
        <div className="flex items-end gap-2 bg-surface border border-rim rounded-xl px-3 py-2 focus-within:border-dawn/50 transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask DAWN anything..."
            rows={1}
            disabled={isStreaming}
            className="flex-1 bg-transparent text-text-primary text-sm placeholder:text-text-muted resize-none outline-none leading-relaxed py-1 max-h-40 disabled:opacity-50"
          />
          <div className="flex items-center gap-1 pb-1">
            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated transition-all"
                title="Clear chat"
              >
                <RotateCcw size={13} />
              </button>
            )}
            <button
              onClick={send}
              disabled={!input.trim() || isStreaming}
              className="w-7 h-7 flex items-center justify-center rounded-lg bg-dawn/90 text-abyss hover:bg-dawn disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <Send size={13} />
            </button>
          </div>
        </div>
        <p className="text-text-muted text-[10px] mt-1.5 px-1">
          Shift+Enter for new line · DAWN searches your knowledge graph before answering
        </p>
      </div>
    </div>
  );
}

function EmptyState() {
  const suggestions = [
    "What's the current status of the Sentinel trading bot?",
    "Explain how Axis handles Uganda PAYE compliance",
    "What are the modules in Regent CRM?",
    "Summarise the EconSim architecture",
  ];

  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 py-12">
      <div className="text-center">
        <div className="w-12 h-12 rounded-2xl bg-dawn/10 border border-dawn/25 flex items-center justify-center mx-auto mb-4">
          <span className="text-dawn text-xl">◈</span>
        </div>
        <h2 className="text-text-primary font-semibold text-lg">DAWN</h2>
        <p className="text-text-muted text-sm mt-1">Digital AI Working Network</p>
      </div>
      <div className="grid grid-cols-1 gap-2 w-full max-w-lg">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => {
              const ta = document.querySelector("textarea");
              if (ta) {
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                  window.HTMLTextAreaElement.prototype, "value"
                )?.set;
                nativeInputValueSetter?.call(ta, s);
                ta.dispatchEvent(new Event("input", { bubbles: true }));
              }
            }}
            className="text-left px-4 py-2.5 rounded-xl bg-surface border border-rim hover:border-dawn/30 text-text-secondary text-sm transition-all hover:text-text-primary"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
