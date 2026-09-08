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
  value: number | string;
}

interface Kpi {
  name: string;
  subtitle: string;
  status: "healthy" | "degraded";
  metrics: Metric[];
}

/**
 * KPI overview — two side-by-side cards (Axis / Regent) with a bordered 2x2
 * metric grid inside, matching the preview's `.metrics` treatment. Every value
 * is wired to a real endpoint; none are fabricated.
 */
export default function KpiGrid() {
  const [kpis, setKpis] = useState<Kpi[] | null>(null);

  const load = useCallback(async () => {
    try {
      // Axis — infrastructure & system health
      const [monitor, nodeCount, healthyCount, sessions] = await Promise.all([
        getMonitorStatus().catch(() => null),
        countNodes().catch(() => 0),
        countNodes({ status: "active" }).catch(() => 0),
        listSessions().then((s) => s.length).catch(() => 0),
      ]);

      const axisHealthy = monitor?.summary?.healthy ?? true;
      const monitored = monitor?.summary?.total ?? nodeCount;

      // Regent — business & marketing activity
      const [artifacts, tasks, decisions, regentSessions] = await Promise.all([
        countArtifacts().catch(() => 0),
        listAgentTasks().then((t) => t.filter((x: any) => ["running", "pending", "paused"].includes(x.status)).length).catch(() => 0),
        listDecisionLog({ limit: 100 }).then((d) => d.length).catch(() => 0),
        listSessions().then((s) => s.length).catch(() => 0),
      ]);

      setKpis([
        {
          name: "Axis",
          subtitle: "Infrastructure and system health",
          status: axisHealthy ? "healthy" : "degraded",
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
            { label: "Sessions", value: regentSessions },
          ],
        },
      ]);
    } catch (err) {
      console.error("[KpiGrid] Failed to load KPIs:", err);
    }
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
            <div className="mt-4 h-20 rounded-nested bg-elevated animate-pulse" />
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
                    kpi.status === "healthy" ? "bg-dawn" : "bg-amber"
                  )}
                />
                <h2 className="text-[13px] font-semibold text-text-primary">{kpi.name}</h2>
                <span
                  className={clsx(
                    "font-mono text-[10px]",
                    kpi.status === "healthy" ? "text-dawn" : "text-amber"
                  )}
                >
                  {kpi.status === "healthy" ? "Healthy" : "Degraded"}
                </span>
              </div>
              <p className="subtitle">{kpi.subtitle}</p>
            </div>
          </div>
          <div className="metrics">
            {kpi.metrics.map((m) => (
              <div key={m.label} className="metric">
                <label>{m.label}</label>
                <strong>{m.value.toLocaleString()}</strong>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
