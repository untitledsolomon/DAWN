"use client";

import { useEffect, useState, useCallback } from "react";
import { Square } from "lucide-react";
import { getAgentLogs, listAgentTasks, cancelAgentTask } from "@/lib/api";
import type { AgentLogEntry, AgentTask } from "@/lib/types";
import { timeAgo } from "@/lib/format";

/**
 * Reframes a raw agent log entry into DAWN's first-person voice where the
 * underlying task string allows it.
 */
function reframeLog(log: AgentLogEntry): string {
  const t = log.task?.trim();
  if (!t) return "I did something.";
  const lower = t.toLowerCase();
  if (/^(i|we|dawn|the system)/.test(lower)) return t;
  return `I ${t.charAt(0).toLowerCase()}${t.slice(1)}`;
}

function RunningRow({ task, onCancel }: { task: AgentTask; onCancel: (id: string) => void }) {
  const progress = typeof task.progress === "number" ? Math.min(100, Math.max(0, task.progress)) : 0;
  const hasProgress = typeof task.progress === "number" && task.progress > 0;
  const step = task.iterations ?? 0;
  return (
    <div className="feedrow running">
      <span className="pulse" />
      <div className="feedtext">
        <div className="flex items-center justify-between gap-3">
          <b className="text-[11px] font-medium text-text-primary">
            I&apos;m working on: {task.goal}
          </b>
          <button
            onClick={() => onCancel(task.id)}
            className="btn"
            style={{ height: 27, padding: "0 8px", fontSize: 10 }}
            title="Interrupt task"
          >
            <Square size={9} className="mr-1 inline-block" />
            Interrupt
          </button>
        </div>
        <div className="progress">
          <i
            style={hasProgress ? { width: `${progress}%` } : { width: "100%", animation: "indeterminate 1.4s ease-in-out infinite" }}
          />
        </div>
        <div className="mono mt-1.5">
          {hasProgress ? `${Math.round(progress)}%` : "working"} · {step} iterations
        </div>
      </div>
    </div>
  );
}

export default function ActivityFeed() {
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [running, setRunning] = useState<AgentTask[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [logData, taskData] = await Promise.all([
        getAgentLogs(20).catch(() => [] as AgentLogEntry[]),
        listAgentTasks().catch(() => [] as AgentTask[]),
      ]);
      setLogs(logData);
      setRunning(taskData.filter((t: AgentTask) => t.status === "running"));
    } catch (err) {
      console.error("[ActivityFeed] Failed to load:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    // Refresh while tasks are running so progress stays live
    const interval = setInterval(() => {
      if (!document.hidden) load();
    }, 8000);
    return () => clearInterval(interval);
  }, [load]);

  const handleCancel = async (id: string) => {
    try {
      await cancelAgentTask(id);
      setRunning((prev) => prev.filter((t) => t.id !== id));
    } catch (err) {
      console.error("[ActivityFeed] Failed to cancel task:", err);
    }
  };

  return (
    <section className="card feed">
      <div className="cardhead">
        <div>
          <p className="eyebrow">Activity</p>
          <h2 className="text-[13px] font-semibold text-text-primary">What I&apos;ve been doing</h2>
        </div>
        <span className="mono">chronological</span>
      </div>

      {loading ? (
        <div className="px-4 py-6 text-center text-text-muted text-xs">Loading activity…</div>
      ) : (
        <>
          {running.map((task) => (
            <RunningRow key={task.id} task={task} onCancel={handleCancel} />
          ))}

          {logs.length === 0 && running.length === 0 ? (
            <div className="px-4 py-6 text-center text-text-muted text-xs">
              No activity yet.
            </div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="feedrow">
                <span className="feeddot" />
                <div className="feedtext">
                  <b className="text-[11px] font-medium text-text-primary">{reframeLog(log)}</b>
                </div>
                <span className="mono">{timeAgo(log.created_at)}</span>
              </div>
            ))
          )}
        </>
      )}
    </section>
  );
}
