"use client";

import { useState, useEffect, useCallback } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  listAgentTasks,
  createAgentTask,
  cancelAgentTask,
  followUpAgentTask,
} from "@/lib/api";
import type { AgentTask } from "@/lib/types";
import {
  ListTodo,
  Plus,
  Trash2,
  Loader2,
  AlertCircle,
  Clock,
  X,
  Play,
  Pause,
  CheckCircle2,
  Wrench,
  GitBranch,
} from "lucide-react";
import clsx from "clsx";

const STATUS_COLORS: Record<string, string> = {
  pending: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  running: "text-dawn bg-dawn/10 border-dawn/20",
  paused: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  completed: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
  failed: "text-ember bg-ember/10 border-ember/20",
  cancelled: "text-text-muted bg-elevated/60 border-rim",
};

const STATUS_ICONS: Record<string, React.ElementType> = {
  pending: Clock,
  running: Loader2,
  paused: Pause,
  completed: CheckCircle2,
  failed: AlertCircle,
  cancelled: X,
};

function AgentTasksContent() {
  const [tasks, setTasks] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Create form state
  const [formOpen, setFormOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [maxIterations, setMaxIterations] = useState(100);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Expanded task detail + follow-up state
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [followingUpId, setFollowingUpId] = useState<string | null>(null);

  const fetchTasks = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listAgentTasks(statusFilter === "all" ? undefined : statusFilter);
      setTasks(data);
      setError(null);
    } catch (err) {
      console.error("[AgentTasks] Failed to load:", err);
      setError("Failed to load agent tasks");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // Poll while any task is running/pending/paused
  useEffect(() => {
    if (!tasks.some((t) => ["running", "pending", "paused"].includes(t.status))) return;
    const interval = setInterval(() => {
      if (!document.hidden) fetchTasks();
    }, 5000);
    return () => clearInterval(interval);
  }, [tasks, fetchTasks]);

  const handleCreate = async () => {
    if (!goal.trim()) return;
    setCreating(true);
    setFormError(null);
    try {
      await createAgentTask({ goal: goal.trim(), max_iterations: maxIterations });
      setGoal("");
      setMaxIterations(100);
      setFormOpen(false);
      await fetchTasks();
    } catch (err) {
      console.error("[AgentTasks] Failed to create:", err);
      setFormError("Failed to create task");
    } finally {
      setCreating(false);
    }
  };

  const handleCancel = async (id: string) => {
    if (!confirm("Cancel this task?")) return;
    try {
      await cancelAgentTask(id);
      await fetchTasks();
    } catch (err) {
      console.error("[AgentTasks] Failed to cancel:", err);
    }
  };

  const handleFollowUp = async (id: string) => {
    if (!followUpText.trim()) return;
    setFollowingUpId(id);
    try {
      await followUpAgentTask(id, followUpText.trim());
      setFollowUpText("");
      await fetchTasks();
    } catch (err) {
      console.error("[AgentTasks] Failed to follow up:", err);
    } finally {
      setFollowingUpId(null);
    }
  };

  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return `${Math.floor(days / 30)}mo ago`;
  };

  const inputClass =
    "w-full bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all";

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 border-b border-rim px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-text-primary text-sm font-semibold">Agent Tasks</h1>
              <p className="text-text-muted text-2xs mt-0.5">
                Long-running tasks DAWN is working on
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-text-muted text-2xs font-mono">{tasks.length} tasks</span>
              <button
                onClick={() => setFormOpen((v) => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all shadow-soft"
              >
                <Plus size={12} />
                {formOpen ? "Close" : "New Task"}
              </button>
            </div>
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-1">
            {["all", "pending", "running", "paused", "completed", "failed", "cancelled"].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={clsx(
                  "px-2 py-1 rounded-md text-2xs font-medium capitalize transition-all",
                  statusFilter === s
                    ? "bg-dawn/15 text-dawn border border-dawn/30"
                    : "text-text-muted hover:text-text-secondary border border-transparent"
                )}
              >
                {s}
              </button>
            ))}
          </div>

          {/* Create form */}
          {formOpen && (
            <div className="mt-3 rounded-xl bg-surface border border-rim shadow-soft p-4 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <h3 className="text-text-primary text-xs font-semibold flex items-center gap-1.5">
                  <ListTodo size={13} className="text-dawn" />
                  New agent task
                </h3>
                <button
                  onClick={() => setFormOpen(false)}
                  className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
                >
                  <X size={12} />
                </button>
              </div>
              <div>
                <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                  Goal
                </label>
                <textarea
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  placeholder="e.g. Research our top 10 competitors and summarize pricing"
                  rows={2}
                  className={clsx(inputClass, "resize-none")}
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Max iterations
                  </label>
                  <input
                    type="number"
                    value={maxIterations}
                    onChange={(e) => setMaxIterations(Number(e.target.value) || 100)}
                    min={1}
                    className={inputClass}
                  />
                </div>
              </div>
              {formError && <p className="text-ember text-2xs">{formError}</p>}
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setFormOpen(false)}
                  className="px-3 py-1.5 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !goal.trim()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all disabled:opacity-40"
                >
                  {creating ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                  Launch Task
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Task list */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="text-dawn animate-spin" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <AlertCircle size={18} className="text-ember" />
              <p className="text-text-muted text-sm">{error}</p>
              <button
                onClick={fetchTasks}
                className="px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
              >
                Retry
              </button>
            </div>
          ) : tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <ListTodo size={24} className="text-text-muted/50" />
              <p className="text-text-muted text-sm">
                {statusFilter === "all"
                  ? "No agent tasks yet. Launch one to get started."
                  : `No ${statusFilter} tasks.`}
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {tasks.map((task) => {
                const Icon = STATUS_ICONS[task.status] || Clock;
                const colorClass = STATUS_COLORS[task.status] || "text-text-muted bg-elevated/60 border-rim";
                return (
                  <div key={task.id} className="p-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 transition-all">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className={clsx("flex items-center gap-1 px-1.5 py-0.5 rounded border text-2xs capitalize", colorClass)}>
                            <Icon size={10} className={task.status === "running" ? "animate-spin" : ""} />
                            {task.status}
                          </span>
                          <span className="text-text-muted text-2xs font-mono">
                            {task.iterations ?? 0} iters
                          </span>
                          <span className="text-text-muted text-2xs flex items-center gap-1">
                            <Clock size={9} />
                            {timeAgo(task.created_at)}
                          </span>
                        </div>
                        <p className="text-text-primary text-sm font-medium">{task.goal}</p>
                        {task.tools_used && task.tools_used.length > 0 && (
                          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                            <Wrench size={10} className="text-text-muted" />
                            {task.tools_used.slice(0, 6).map((tool) => (
                              <span key={tool} className="px-1.5 py-0.5 rounded bg-elevated/60 text-text-muted text-2xs font-mono">
                                {tool}
                              </span>
                            ))}
                          </div>
                        )}
                        {typeof task.progress === "number" && task.progress > 0 && (
                          <div className="mt-2 h-1 rounded-full bg-elevated overflow-hidden">
                            <div
                              className="h-full bg-dawn rounded-full transition-all"
                              style={{ width: `${Math.min(100, task.progress)}%` }}
                            />
                          </div>
                        )}
                        {(task.status === "completed" || task.status === "failed") && (
                          <button
                            onClick={() => setExpandedId(expandedId === task.id ? null : task.id)}
                            className="mt-2 text-2xs text-dawn hover:text-dawn/80 transition-all"
                          >
                            {expandedId === task.id ? "Hide result" : "View result"}
                          </button>
                        )}
                      </div>
                      {(task.status === "running" || task.status === "pending" || task.status === "paused") && (
                        <button
                          onClick={() => handleCancel(task.id)}
                          className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-ember hover:bg-ember/10 transition-all flex-shrink-0"
                          title="Cancel"
                        >
                          <X size={13} />
                        </button>
                      )}
                    </div>

                    {/* Expanded result + follow-up */}
                    {expandedId === task.id && (task.status === "completed" || task.status === "failed") && (
                      <div className="mt-3 pt-3 border-t border-rim space-y-3">
                        {task.error && (
                          <div className="px-3 py-2 rounded-lg bg-ember/5 border border-ember/15 text-ember text-2xs font-mono break-words">
                            {task.error}
                          </div>
                        )}
                        {task.result ? (
                          <div className="px-3 py-2.5 rounded-lg bg-elevated/40 border border-rim text-text-secondary text-xs whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
                            {task.result}
                          </div>
                        ) : (
                          !task.error && (
                            <p className="text-text-muted text-2xs">No report was produced for this task.</p>
                          )
                        )}
                        <div className="flex items-end gap-2">
                          <textarea
                            value={followUpText}
                            onChange={(e) => setFollowUpText(e.target.value)}
                            placeholder="Follow up on this task…"
                            rows={2}
                            className="flex-1 bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all resize-none"
                          />
                          <button
                            onClick={() => handleFollowUp(task.id)}
                            disabled={followingUpId === task.id || !followUpText.trim()}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all disabled:opacity-40 flex-shrink-0"
                          >
                            {followingUpId === task.id ? <Loader2 size={11} className="animate-spin" /> : <Play size={11} />}
                            Follow up
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function AgentTasksPage() {
  return (
    <AppShell>
      <AgentTasksContent />
    </AppShell>
  );
}
