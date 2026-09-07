"use client";

import { useState, type ReactNode } from "react";
import {
  ChevronDown,
  Search,
  GitBranch,
  Tag,
  Cpu,
  FileText,
  Package,
  Check,
  X,
  Wrench,
  Loader2,
} from "lucide-react";
import clsx from "clsx";

// ── Types ─────────────────────────────────────────────────────────────────

interface ChatToolCall {
  name: string;
  args: Record<string, unknown>;
  result_count?: number;
}

interface AgentToolEntry {
  call: { name: string; args: Record<string, unknown> };
  result?: {
    success: boolean;
    output: unknown;
    error: string | null;
  };
}

// ── Icons ─────────────────────────────────────────────────────────────────

const ICONS: Record<string, ReactNode> = {
  fuzzy_search: <Search size={12} />,
  hybrid_search: <Search size={12} />,
  semantic_search: <Cpu size={12} />,
  traverse: <GitBranch size={12} />,
  search_tags: <Tag size={12} />,
  filesystem: <FileText size={12} />,
  git: <GitBranch size={12} />,
  web_search: <Search size={12} />,
  install_skill: <Package size={12} />,
};

function iconFor(name: string): ReactNode {
  if (ICONS[name]) return ICONS[name];
  if (name.startsWith("skill_")) return <Package size={12} />;
  return <Wrench size={12} />;
}

// ── Helpers ───────────────────────────────────────────────────────────────

function formatArg(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function firstArg(args: Record<string, unknown>): string {
  const v = Object.values(args)[0];
  return formatArg(v);
}

function formatOutput(output: unknown): string {
  if (output === null || output === undefined) return "";
  if (typeof output === "string") return output;
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

function truncate(s: string, n = 60): string {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ── Component ──────────────────────────────────────────────────────────────

interface Props {
  // chat mode: knowledge-graph search tool calls
  toolCalls?: ChatToolCall[];
  // agent mode: real executed tool calls with results
  trace?: AgentToolEntry[];
  // live streaming state
  thinking?: boolean;
}

export default function ToolCallView({ toolCalls, trace, thinking }: Props) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const toggle = (i: number) =>
    setExpanded((prev: Record<number, boolean>) => ({
      ...prev,
      [i]: !prev[i],
    }));

  // Live thinking state (no calls yet)
  if (thinking && !toolCalls?.length && !trace?.length) {
    return (
      <div className="flex items-center gap-2 mb-2">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-dawn/8 border border-dawn/15 text-dawn text-2xs font-mono">
          <Loader2 size={11} className="animate-spin" />
          working…
        </span>
      </div>
    );
  }

  // Agent mode: render each executed tool as a collapsible card
  if (trace && trace.length > 0) {
    return (
      <div className="flex flex-col gap-1.5 mb-3">
        {trace.map((entry, i) => {
          const pending = !entry.result;
          const success = entry.result?.success;
          const isOpen = expanded[i];
          return (
            <div
              key={i}
              className={clsx(
                "rounded-lg border bg-surface transition-colors",
                pending
                  ? "border-dawn/20"
                  : success
                    ? "border-rim"
                    : "border-error/25",
              )}
            >
              <button
                onClick={() => toggle(i)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left"
              >
                <span className="text-dawn flex-shrink-0">
                  {iconFor(entry.call.name)}
                </span>
                <span className="text-text-primary text-xs font-medium font-mono flex-shrink-0">
                  {entry.call.name}
                </span>
                {firstArg(entry.call.args) && (
                <span className="text-text-muted text-2xs font-mono truncate flex-1 min-w-0">
                  {truncate(firstArg(entry.call.args))}
                </span>
                )}
                <span className="flex-shrink-0 flex items-center gap-1">
                  {pending ? (
                    <Loader2 size={11} className="text-dawn animate-spin" />
                  ) : success ? (
                    <Check size={12} className="text-success" />
                  ) : (
                    <X size={12} className="text-error" />
                  )}
                  <ChevronDown
                    size={12}
                    className={clsx(
                      "text-text-muted transition-transform",
                      isOpen && "rotate-180",
                    )}
                  />
                </span>
              </button>

              {isOpen && (
                <div className="px-2.5 pb-2.5 pt-1 border-t border-rim/70 space-y-2">
                  {/* Args */}
                  <div>
                    <p className="text-2xs font-mono uppercase tracking-wider text-text-muted mb-1">
                      Arguments
                    </p>
                    <pre className="text-2xs font-mono bg-elevated/50 border border-rim rounded-md p-2 overflow-x-auto text-text-secondary whitespace-pre-wrap break-words">
                      {JSON.stringify(entry.call.args, null, 2) || "{}"}
                    </pre>
                  </div>

                  {/* Result */}
                  {!pending && (
                    <div>
                      <p className="text-2xs font-mono uppercase tracking-wider text-text-muted mb-1">
                        {success ? "Result" : "Error"}
                      </p>
                      <pre
                        className={clsx(
                          "text-2xs font-mono border rounded-md p-2 overflow-x-auto whitespace-pre-wrap break-words",
                          success
                            ? "bg-elevated/50 border-rim text-text-secondary"
                            : "bg-error/5 border-error/25 text-error",
                        )}
                      >
                        {success
                          ? truncate(formatOutput(entry.result?.output), 600)
                          : entry.result?.error || "Tool failed"}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Chat mode: render search tool calls as a compact collapsible group
  if (toolCalls && toolCalls.length > 0) {
    const isOpen = expanded[0];
    return (
      <div className="mb-3">
        <button
          onClick={() => toggle(0)}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-surface border border-rim hover:border-dawn/30 text-text-muted text-2xs font-mono transition-colors"
        >
          <Search size={11} className="text-dawn" />
          <span>{toolCalls.length} search call{toolCalls.length > 1 ? "s" : ""}</span>
          <ChevronDown
            size={11}
            className={clsx("transition-transform", isOpen && "rotate-180")}
          />
        </button>

        {isOpen && (
          <div className="mt-1.5 flex flex-col gap-1">
            {toolCalls.map((tc, i) => (
              <div
                key={i}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-surface border border-rim"
              >
                <span className="text-dawn flex-shrink-0">
                  {iconFor(tc.name)}
                </span>
                <span className="text-text-primary text-xs font-mono flex-shrink-0">
                  {tc.name}
                </span>
                {tc.args && firstArg(tc.args) && (
                  <span className="text-text-muted text-2xs font-mono truncate flex-1 min-w-0">
                    {truncate(firstArg(tc.args))}
                  </span>
                )}
                {tc.result_count != null && (
                  <span className="text-dawn/70 text-2xs font-mono flex-shrink-0">
                    → {tc.result_count}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return null;
}
