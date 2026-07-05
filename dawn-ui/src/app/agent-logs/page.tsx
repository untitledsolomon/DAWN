"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  FileText,
  GitBranch,
  Search,
  Package,
  RefreshCw,
  ChevronDown,
  Zap,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { getAgentLogs } from "@/lib/api";
import type { AgentLogEntry } from "@/lib/types";

const TOOL_ICONS: Record<string, React.ReactNode> = {
  filesystem: <FileText size={10} />,
  git: <GitBranch size={10} />,
  web_search: <Search size={10} />,
  install_skill: <Package size={10} />,
};

export default function AgentLogsPage() {
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "success" | "error" | "running">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getAgentLogs(50, filter === "all" ? undefined : filter);
      setLogs(data);
    } catch (e) {
      console.error("[AgentLogs] Failed to load:", e);
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const formatDuration = (ms?: number) => {
    if (!ms) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const STATUS_CONFIG = {
    success: { icon: CheckCircle, color: "text-success", bg: "bg-success/10", border: "border-success/20", label: "Success" },
    error: { icon: XCircle, color: "text-error", bg: "bg-error/10", border: "border-error/20", label: "Error" },
    running: { icon: Clock, color: "text-dawn", bg: "bg-dawn/10", border: "border-dawn/20", label: "Running" },
  };

  const FILTERS = [
    { id: "all" as const, label: "All", count: logs.length },
    { id: "success" as const, label: "Success", count: logs.filter((l) => l.status === "success").length },
    { id: "error" as const, label: "Error", count: logs.filter((l) => l.status === "error").length },
    { id: "running" as const, label: "Running", count: logs.filter((l) => l.status === "running").length },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="min-w-0">
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Agent Logs</h1>
            <p className="text-text-muted text-2xs hidden sm:block">Monitor agent task executions and tool calls</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="text-text-muted text-2xs font-mono bg-elevated/50 border border-rim px-2 py-1 rounded-lg hidden xs:inline">
              {logs.length} total
            </span>
            <button
              onClick={load}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {/* Filters */}
        <div className="flex items-center gap-2 px-4 sm:px-6 py-2.5 border-b border-rim flex-shrink-0 overflow-x-auto">
          {FILTERS.map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all whitespace-nowrap ${
                filter === id
                  ? "bg-dawn/10 border-dawn/30 text-dawn"
                  : "bg-surface border-rim text-text-muted hover:text-text-secondary"
              }`}
            >
              {label}
              <span className={`text-2xs font-mono ${
                filter === id ? "text-dawn/70" : "text-text-muted"
              }`}>
                {count}
              </span>
            </button>
          ))}
        </div>

        {/* Log entries */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : logs.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Activity size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">No agent logs yet</p>
              <p className="text-text-muted text-xs">Run an agent task in Chat to see logs here</p>
            </div>
          ) : (
            <div className="space-y-2 max-w-3xl">
              {logs.map((entry) => {
                const cfg = STATUS_CONFIG[entry.status];
                const Icon = cfg.icon;
                const isExpanded = expandedId === entry.id;

                return (
                  <div
                    key={entry.id}
                    className="bg-surface border border-rim rounded-xl overflow-hidden hover:border-dawn/20 transition-all group"
                  >
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : entry.id)}
                      className="w-full text-left px-4 py-3 flex items-start justify-between gap-3"
                    >
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        {/* Status icon */}
                        <div className={`w-7 h-7 rounded-lg ${cfg.bg} border ${cfg.border} flex items-center justify-center flex-shrink-0 mt-0.5`}>
                          <Icon size={13} className={cfg.color} />
                        </div>

                        <div className="min-w-0 flex-1">
                          <p className="text-text-primary text-sm font-medium truncate">{entry.task}</p>
                          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                            {(entry.tools_used || []).map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono"
                              >
                                <span className="text-dawn">{TOOL_ICONS[tool] || null}</span>
                                {tool}
                              </span>
                            ))}
                            {entry.model && (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-dawn/5 border border-dawn/15 text-dawn text-2xs font-mono">
                                <Zap size={8} />
                                {entry.model}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-3 flex-shrink-0">
                        <div className="text-right hidden xs:block">
                          <p className="text-text-muted text-2xs font-mono">{formatDuration(entry.duration_ms)}</p>
                          <p className="text-text-muted text-2xs font-mono">{entry.tokens_used > 0 ? `${entry.tokens_used} tok` : "—"}</p>
                        </div>
                        <span className="text-text-muted text-2xs font-mono opacity-0 group-hover:opacity-100 transition-opacity hidden sm:block">
                          {timeAgo(entry.created_at)}
                        </span>
                        <ChevronDown
                          size={12}
                          className={`text-text-muted transition-transform flex-shrink-0 ${isExpanded ? "rotate-180" : ""}`}
                        />
                      </div>
                    </button>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="border-t border-rim px-4 py-3 bg-elevated/20 space-y-2">
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                          <div>
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Duration</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5">{formatDuration(entry.duration_ms)}</p>
                          </div>
                          <div>
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Tokens</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5">{entry.tokens_used > 0 ? entry.tokens_used.toLocaleString() : "—"}</p>
                          </div>
                          <div className="col-span-2 sm:col-span-1">
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Model</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5 capitalize">{entry.model || "—"}</p>
                          </div>
                        </div>

                        {entry.status === "error" && entry.error_message && (
                          <div className="mt-2 px-3 py-2 rounded-lg bg-error/5 border border-error/15 text-error text-2xs font-mono break-words">
                            {entry.error_message}
                          </div>
                        )}

                        {entry.status === "running" && (
                          <div className="mt-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
                            <span className="text-dawn text-2xs font-mono">Executing...</span>
                          </div>
                        )}

                        {entry.completed_at && (
                          <div className="mt-2 text-text-muted text-2xs font-mono">
                            Completed: {new Date(entry.completed_at).toLocaleString()}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
