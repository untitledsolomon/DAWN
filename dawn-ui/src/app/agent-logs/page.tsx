"use client";

import { useState } from "react";
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
  Filter,
  ChevronDown,
  Zap,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

// ── Mock data ─────────────────────────────────────────────────────────────────────

interface AgentLogEntry {
  id: string;
  timestamp: Date;
  status: "success" | "error" | "running";
  task: string;
  tools: string[];
  duration: string;
  tokens: number;
  model?: string;
}

const MOCK_LOGS: AgentLogEntry[] = [
  {
    id: "1",
    timestamp: new Date(Date.now() - 1000 * 60 * 5),
    status: "success",
    task: "Search web for latest DeepSeek model release",
    tools: ["web_search"],
    duration: "3.2s",
    tokens: 1240,
    model: "deepseek",
  },
  {
    id: "2",
    timestamp: new Date(Date.now() - 1000 * 60 * 15),
    status: "success",
    task: "List files in sandbox and show structure",
    tools: ["filesystem"],
    duration: "1.8s",
    tokens: 890,
    model: "deepseek",
  },
  {
    id: "3",
    timestamp: new Date(Date.now() - 1000 * 60 * 45),
    status: "error",
    task: "Clone repo and analyze dependencies",
    tools: ["git", "filesystem"],
    duration: "12.5s",
    tokens: 3400,
    model: "deepseek",
  },
  {
    id: "4",
    timestamp: new Date(Date.now() - 1000 * 60 * 120),
    status: "success",
    task: "Write README.md to sandbox",
    tools: ["filesystem"],
    duration: "2.1s",
    tokens: 560,
    model: "deepseek",
  },
  {
    id: "5",
    timestamp: new Date(Date.now() - 1000 * 60 * 180),
    status: "running",
    task: "Analyze EconSim codebase and generate docs",
    tools: ["filesystem", "git", "web_search"],
    duration: "—",
    tokens: 0,
    model: "deepseek",
  },
  {
    id: "6",
    timestamp: new Date(Date.now() - 1000 * 60 * 300),
    status: "success",
    task: "Check Jarvis agent status on Paperclip VPS",
    tools: ["filesystem"],
    duration: "0.9s",
    tokens: 320,
    model: "local",
  },
];

const TOOL_ICONS: Record<string, React.ReactNode> = {
  filesystem: <FileText size={10} />,
  git: <GitBranch size={10} />,
  web_search: <Search size={10} />,
  install_skill: <Package size={10} />,
};

// ── Component ─────────────────────────────────────────────────────────────────────

export default function AgentLogsPage() {
  const [filter, setFilter] = useState<"all" | "success" | "error" | "running">("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = filter === "all"
    ? MOCK_LOGS
    : MOCK_LOGS.filter((l) => l.status === filter);

  const timeAgo = (date: Date) => {
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  const STATUS_CONFIG = {
    success: { icon: CheckCircle, color: "text-success", bg: "bg-success/10", border: "border-success/20", label: "Success" },
    error: { icon: XCircle, color: "text-error", bg: "bg-error/10", border: "border-error/20", label: "Error" },
    running: { icon: Clock, color: "text-dawn", bg: "bg-dawn/10", border: "border-dawn/20", label: "Running" },
  };

  const FILTERS = [
    { id: "all" as const, label: "All", count: MOCK_LOGS.length },
    { id: "success" as const, label: "Success", count: MOCK_LOGS.filter((l) => l.status === "success").length },
    { id: "error" as const, label: "Error", count: MOCK_LOGS.filter((l) => l.status === "error").length },
    { id: "running" as const, label: "Running", count: MOCK_LOGS.filter((l) => l.status === "running").length },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Agent Logs</h1>
            <p className="text-text-muted text-2xs">Monitor agent task executions and tool calls</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-text-muted text-2xs font-mono bg-elevated/50 border border-rim px-2 py-1 rounded-lg">
              {MOCK_LOGS.length} total
            </span>
            <button className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <RefreshCw size={14} />
            </button>
          </div>
        </header>

        {/* Filters */}
        <div className="flex items-center gap-2 px-6 py-2.5 border-b border-rim flex-shrink-0">
          {FILTERS.map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setFilter(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
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
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Activity size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">No agent logs match this filter</p>
            </div>
          ) : (
            <div className="space-y-2 max-w-3xl">
              {filtered.map((entry) => {
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
                            {entry.tools.map((tool) => (
                              <span
                                key={tool}
                                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono"
                              >
                                <span className="text-dawn">{TOOL_ICONS[tool]}</span>
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
                        <div className="text-right">
                          <p className="text-text-muted text-2xs font-mono">{entry.duration}</p>
                          <p className="text-text-muted text-2xs font-mono">{entry.tokens > 0 ? `${entry.tokens} tok` : "—"}</p>
                        </div>
                        <span className="text-text-muted text-2xs font-mono opacity-0 group-hover:opacity-100 transition-opacity">
                          {timeAgo(entry.timestamp)}
                        </span>
                        <ChevronDown
                          size={12}
                          className={`text-text-muted transition-transform ${isExpanded ? "rotate-180" : ""}`}
                        />
                      </div>
                    </button>

                    {/* Expanded details */}
                    {isExpanded && (
                      <div className="border-t border-rim px-4 py-3 bg-elevated/20 space-y-2">
                        <div className="grid grid-cols-3 gap-4">
                          <div>
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Duration</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5">{entry.duration}</p>
                          </div>
                          <div>
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Tokens</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5">{entry.tokens > 0 ? entry.tokens.toLocaleString() : "—"}</p>
                          </div>
                          <div>
                            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Model</p>
                            <p className="text-text-primary text-xs font-mono mt-0.5 capitalize">{entry.model || "—"}</p>
                          </div>
                        </div>

                        {entry.status === "error" && (
                          <div className="mt-2 px-3 py-2 rounded-lg bg-error/5 border border-error/15 text-error text-2xs font-mono">
                            Git clone failed: repository not found or access denied
                          </div>
                        )}

                        {entry.status === "running" && (
                          <div className="mt-2 flex items-center gap-1.5">
                            <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
                            <span className="text-dawn text-2xs font-mono">Executing...</span>
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
