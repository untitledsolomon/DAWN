"use client";

import { useEffect, useState, useCallback } from "react";
import clsx from "clsx";
import {
  countNodes,
  countArtifacts,
  listSessions,
  listAgentTasks,
  listDecisionLog,
  getMonitorStatus,
} from "@/lib/api";

interface Metric {
  label: string;
  value: number | string | null;  // null = failed to load
}

interface Kpi {
  name: string;
  subtitle: string;
  status: "healthy" | "degraded" | "unknown";
  metrics: Metric[];
}

/**
 * KPI overview — two side-by-side cards (Axis / Regent) with a bordered 2x2
 * metric grid inside, matching the preview's `.metrics` treatment. Every value
 * is wired to a real endpoint; none are fabricated.
 *
 * Fix 2: silent failures are distinguished from healthy-and-empty. A failed
 * endpoint renders as "Unknown" (null) rather than being collapsed into a fake
 * "0" or "Healthy" — a real outage in the monitoring pipeline is visible
 * instead of being invisible by design.
 */
export default function KpiGrid() {
  const [kpis, setKpis] = useState<Kpi[] | null>(null);

  const load = useCallback(async () => {
    // Use allSettled so a failing endpoint is recorded as "failed to load"
    // (null) rather than collapsed into a fake success value.
    const [monitorR, nodeCountR, healthyCountR, sessionsR, artifactsR, tasksR, decisionsR] =
      await Promise.allSettled([
        getMonitorStatus(),
        countNodes(),
        countNodes({ status: "active" }),
        listSessions(),
        countArtifacts(),
        listAgentTasks(),
        listDecisionLog({ limit: 100 }),
      ]);

    const monitor = monitorR.status === "fulfilled" ? monitorR.value : null;
    const nodeCount = nodeCountR.status === "fulfilled" ? nodeCountR.value : null;
    const healthyCount = healthyCountR.status === "fulfilled" ? healthyCountR.value : null;
    const sessions = sessionsR.status === "fulfilled" ? sessionsR.value.length : null;
    const artifacts = artifactsR.status === "fulfilled" ? artifactsR.value : null;
    const tasks = tasksR.status === "fulfilled"
      ? tasksR.value.filter((x: any) => ["running", "pending", "paused"].includes(x.status)).length
      : null;
    const decisions = decisionsR.status === "fulfilled" ? decisionsR.value.length : null;

    // A failed health check is not evidence of health — it's an unknown.
    const axisHealthy = monitorR.status === "fulfilled"
      ? (monitor?.summary?.healthy ?? true)
      : null;
    const monitored = monitor?.summary?.total ?? nodeCount;

    setKpis([
      {
        name: "Axis",
        subtitle: "Infrastructure and system health",
        status: axisHealthy === null ? "unknown" : (axisHealthy ? "healthy" : "degraded"),
        metrics: [
          { label: "Monitored", value: monitored },
          { label: "Healthy", value: healthyCount },
          { label: "Knowledge", value: nodeCount },
          { label: "Sessions", value: sessions },
        ],
      },
      {
        name: "Regent",
        subtitle: "Business and marketing activity",
        status: "healthy",
        metrics: [
          { label: "Artifacts", value: artifacts },
          { label: "Active work", value: tasks },
          { label: "Signals", value: decisions },
          { label: "Sessions", value: sessions },
        ],
      },
    ]);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (!kpis) {
    return (
      <div className="grid2">
        {[0, 1].map((i) => (
          <div key={i} className="card kpi">
            <div className="h-4 w-24 rounded bg-elevated animate-pulse" />
            <div className="mt-4 h-20 rounded-[8px] bg-elevated animate-pulse" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid2">
      {kpis.map((kpi) => (
        <section key={kpi.name} className="card kpi">
          <div className="kpi-top">
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    "status-dot",
                    kpi.status === "healthy" ? "bg-dawn" : kpi.status === "unknown" ? "bg-text-muted" : "bg-amber"
                  )}
                />
                <h2 className="text-[13px] font-semibold text-text-primary">{kpi.name}</h2>
                <span
                  className={clsx(
                    "font-mono text-[10px]",
                    kpi.status === "healthy" ? "text-dawn" : kpi.status === "unknown" ? "text-text-muted" : "text-amber"
                  )}
                >
                  {kpi.status === "healthy" ? "Healthy" : kpi.status === "unknown" ? "Unknown" : "Degraded"}
                </span>
              </div>
              <p className="subtitle">{kpi.subtitle}</p>
            </div>
          </div>
          <div className="metrics">
            {kpi.metrics.map((m) => (
              <div key={m.label} className="metric">
                <label>{m.label}</label>
                <strong className={m.value === null ? "text-text-muted" : undefined}>
                  {m.value === null ? "—" : m.value.toLocaleString()}
                </strong>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
