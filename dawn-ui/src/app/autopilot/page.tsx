"use client";

import { useCallback, useEffect, useState } from "react";
import { Bot, ChevronDown, Plus, Play, Eye, RotateCcw, Pause, Octagon } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import {
  getAutopilotStatus,
  killAutopilot,
  listAutopilotJobs,
  createAutopilotJob,
  patchAutopilotJob,
  runAutopilotJob,
  pauseAutopilotJob,
  resumeAutopilotJob,
  listAutopilotRuns,
  feedbackAutopilotRun,
  setRuntimeSetting,
  type AutopilotJob,
  type AutopilotRun,
  type AutopilotStatus,
} from "@/lib/api";
import clsx from "clsx";

const STATUS_BADGE: Record<string, string> = {
  running: "bg-dawn/10 text-dawn",
  quiet: "bg-elevated text-text-muted",
  completed: "bg-success/10 text-success",
  needs_attention: "bg-amber-500/10 text-amber-600",
  failed: "bg-ember/10 text-ember",
  budget_stopped: "bg-ember/10 text-ember",
  cancelled: "bg-elevated text-text-muted",
  skipped: "bg-elevated text-text-muted",
};

export default function AutopilotPage() {
  const [status, setStatus] = useState<AutopilotStatus | null>(null);
  const [jobs, setJobs] = useState<AutopilotJob[]>([]);
  const [runs, setRuns] = useState<Record<string, AutopilotRun[]>>({});
  const [openJob, setOpenJob] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // new-job form
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [cron, setCron] = useState("0 8,16 * * 1-5");
  const [autonomy, setAutonomy] = useState<"observe" | "propose">("observe");

  const flash = (m: string) => {
    setMsg(m);
    setTimeout(() => setMsg(null), 3000);
  };

  const load = useCallback(async () => {
    try {
      setStatus(await getAutopilotStatus());
      setJobs(await listAutopilotJobs());
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to load autopilot");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggleMaster = async (enabled: boolean) => {
    try {
      await setRuntimeSetting("autopilot.enabled", enabled);
      setStatus((s) => (s ? { ...s, enabled } : s));
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to toggle autopilot");
    }
  };

  const stopEverything = async () => {
    if (!window.confirm("Stop everything? Running jobs finish their current step, then stop.")) return;
    try {
      await killAutopilot();
      if (status) setStatus({ ...status, enabled: false });
      flash("Autopilot stopped");
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to stop");
    }
  };

  const toggleEnabled = async (job: AutopilotJob) => {
    try {
      await patchAutopilotJob(job.id, { enabled: !job.enabled });
      load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to update job");
    }
  };

  const runNow = async (job: AutopilotJob, dry: boolean) => {
    setBusyId(job.id);
    try {
      const res = await runAutopilotJob(job.id, dry);
      flash(`Run ${res.status}`);
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to run job");
    } finally {
      setBusyId(null);
    }
  };

  const toggleRuns = async (jobId: string) => {
    if (openJob === jobId) {
      setOpenJob(null);
      return;
    }
    setOpenJob(jobId);
    try {
      const rows = await listAutopilotRuns(jobId, 10);
      setRuns((prev) => ({ ...prev, [jobId]: rows }));
    } catch {
      setRuns((prev) => ({ ...prev, [jobId]: [] }));
    }
  };

  const feedback = async (runId: string, value: "useful" | "noise") => {
    try {
      await feedbackAutopilotRun(runId, value);
      if (openJob) toggleRuns(openJob);
    } catch {
      flash("Failed to record feedback");
    }
  };

  const createJob = async () => {
    if (!name.trim() || !goal.trim()) return;
    try {
      await createAutopilotJob({ name, goal, autonomy, schedule: cron ? { cron, timezone: "Africa/Kampala" } : null });
      setName("");
      setGoal("");
      setShowNew(false);
      load();
    } catch (e) {
      flash(e instanceof Error ? e.message : "Failed to create job");
    }
  };

  const toggle = (job: AutopilotJob) => {
    if (job.paused_reason) {
      resumeAutopilotJob(job.id).then(load).catch((e) => flash(String(e)));
    } else if (job.enabled) {
      pauseAutopilotJob(job.id).then(load).catch((e) => flash(String(e)));
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <div className="flex-shrink-0 px-6 sm:px-7 pt-5">
          <div className="max-w-[980px] mx-auto">
            <div className="flex items-center justify-between">
              <div>
                <p className="eyebrow">Autonomy</p>
                <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">Autopilot</h1>
              </div>
              <button
                onClick={stopEverything}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-ember border border-ember/40 hover:bg-ember/5 transition-all"
              >
                <Octagon size={12} /> Stop everything
              </button>
            </div>

            <div className="mt-4 bg-surface border border-rim rounded-xl p-4 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className={clsx("w-2.5 h-2.5 rounded-full", status?.enabled ? "bg-success" : "bg-ember")} />
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    Autopilot {status?.enabled ? "ON" : "OFF"}
                  </p>
                  <p className="text-2xs text-text-muted mt-0.5">
                    {status ? `${status.runs_today} runs today · ${status.quiet} quiet · ${status.tokens_today?.toLocaleString()} tokens` : "…"}
                  </p>
                </div>
              </div>
              <button
                onClick={() => toggleMaster(!status?.enabled)}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all",
                  status?.enabled ? "bg-surface text-text-secondary border border-rim" : "bg-dawn/90 text-white hover:bg-dawn",
                )}
              >
                {status?.enabled ? "Turn off" : "Turn on"}
              </button>
            </div>

            {msg && <p className="mt-2 text-2xs text-dawn">{msg}</p>}

            <div className="mt-4 flex items-center justify-between">
              <p className="text-text-muted text-xs">Scheduled and event-triggered jobs</p>
              <button
                onClick={() => setShowNew(!showNew)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn transition-all"
              >
                <Plus size={12} /> New job
              </button>
            </div>

            {showNew && (
              <div className="mt-3 bg-surface border border-rim rounded-xl p-4 space-y-3">
                <input
                  value={name} onChange={(e) => setName(e.target.value)} placeholder="Name"
                  className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-dawn/50"
                />
                <textarea
                  value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Goal prompt" rows={3}
                  className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-dawn/50"
                />
                <div className="flex gap-2">
                  <input
                    value={cron} onChange={(e) => setCron(e.target.value)} placeholder="cron (e.g. 0 8,16 * * 1-5)"
                    className="flex-1 bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm font-mono text-text-primary outline-none focus:border-dawn/50"
                  />
                  <select
                    value={autonomy} onChange={(e) => setAutonomy(e.target.value as "observe" | "propose")}
                    className="bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none"
                  >
                    <option value="observe">Observe</option>
                    <option value="propose">Propose</option>
                  </select>
                  <button
                    onClick={createJob}
                    disabled={!name.trim() || !goal.trim()}
                    className="px-4 py-2 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn disabled:opacity-30"
                  >
                    Create
                  </button>
                </div>
                <p className="text-2xs text-text-muted">Created disabled. Enable after reviewing.</p>
              </div>
            )}

            <div className="mt-3 space-y-3 pb-8">
              {jobs.map((job) => (
                <JobCard
                  key={job.id}
                  job={job}
                  busy={busyId === job.id}
                  runs={openJob === job.id ? (runs[job.id] ?? []) : undefined}
                  onToggle={() => toggleEnabled(job)}
                  onRun={(dry) => runNow(job, dry)}
                  onToggleRuns={() => toggleRuns(job.id)}
                  onPauseResume={() => toggle(job)}
                  onFeedback={feedback}
                />
              ))}
              {jobs.length === 0 && (
                <p className="text-text-muted text-2xs py-6 text-center">No jobs yet. Create one to start.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}

function JobCard({
  job,
  busy,
  runs,
  onToggle,
  onRun,
  onToggleRuns,
  onPauseResume,
  onFeedback,
}: {
  job: AutopilotJob;
  busy: boolean;
  runs?: AutopilotRun[];
  onToggle: () => void;
  onRun: (dry: boolean) => void;
  onToggleRuns: () => void;
  onPauseResume: () => void;
  onFeedback: (runId: string, v: "useful" | "noise") => void;
}) {
  const scheduleText = job.schedule?.cron ?? (job.triggers.length ? `on ${job.triggers.map((t) => t.event).join(", ")}` : "manual");
  return (
    <div className={clsx("bg-surface border rounded-xl overflow-hidden", job.enabled ? "border-dawn/30" : "border-rim")}>
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Bot size={14} className={job.enabled ? "text-dawn" : "text-text-muted"} />
              <span className="text-sm font-medium text-text-primary">{job.name}</span>
              <span className="text-2xs font-mono px-1.5 py-0.5 rounded bg-elevated text-text-muted">{job.autonomy}</span>
              {job.paused_reason && <span className="text-2xs px-1.5 py-0.5 rounded bg-ember/10 text-ember">paused</span>}
            </div>
            {job.description && <p className="text-text-muted text-xs mt-1">{job.description}</p>}
            <p className="text-2xs text-text-muted mt-1.5 font-mono">
              {scheduleText} · next run: {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : "—"}
            </p>
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <button
              onClick={() => onRun(false)}
              disabled={busy}
              title="Run now"
              className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-dawn hover:bg-dawn/5 disabled:opacity-30"
            >
              <Play size={13} />
            </button>
            <button
              onClick={() => onRun(true)}
              disabled={busy}
              title="Dry run (observe, no notifications)"
              className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60 disabled:opacity-30"
            >
              <Eye size={13} />
            </button>
            <button
              onClick={onPauseResume}
              title={job.paused_reason ? "Resume" : "Pause"}
              className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60"
            >
              {job.paused_reason ? <RotateCcw size={13} /> : <Pause size={13} />}
            </button>
            <button
              onClick={onToggle}
              className={clsx(
                "px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
                job.enabled
                  ? "bg-dawn/15 text-dawn border-dawn/30"
                  : "bg-surface text-text-muted border-rim hover:text-text-secondary",
              )}
            >
              {job.enabled ? "ON" : "OFF"}
            </button>
            <button onClick={onToggleRuns} className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary">
              <ChevronDown size={13} className={clsx("transition-transform", runs && "rotate-180")} />
            </button>
          </div>
        </div>

        {runs && (
          <div className="mt-3 border-t border-rim pt-3 space-y-2">
            {runs.length === 0 && <p className="text-2xs text-text-muted">No runs yet.</p>}
            {runs.map((r) => (
              <div key={r.id} className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <span className={clsx("inline-block text-2xs px-1.5 py-0.5 rounded font-mono", STATUS_BADGE[r.status] ?? "bg-elevated text-text-muted")}>
                    {r.status}
                  </span>
                  <span className="text-2xs text-text-muted ml-2 font-mono">{r.tokens_out} out</span>
                  <p className="text-xs text-text-secondary mt-0.5 truncate">{r.summary || r.error || r.status}</p>
                </div>
                <div className="flex items-center gap-1 flex-shrink-0">
                  {r.status === "quiet" || r.status === "completed" ? (
                    <>
                      <button onClick={() => onFeedback(r.id, "useful")} className="text-2xs px-2 py-1 rounded text-success hover:bg-success/10">Useful</button>
                      <button onClick={() => onFeedback(r.id, "noise")} className="text-2xs px-2 py-1 rounded text-ember hover:bg-ember/10">Noise</button>
                    </>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
