"use client";

import { useEffect, useState } from "react";
import { Shield, ShieldCheck } from "lucide-react";
import clsx from "clsx";
import { listConfiguredTools, type ConfiguredTool } from "@/lib/api";

const RISK_COLORS: Record<string, string> = {
  read: "bg-success/10 text-success",
  internal_write: "bg-dawn/10 text-dawn",
  external_write: "bg-amber-500/10 text-amber-600",
  exec: "bg-ember/10 text-ember",
};

export default function ToolsSection() {
  const [tools, setTools] = useState<ConfiguredTool[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listConfiguredTools()
      .then(setTools)
      .catch(() => setTools([]))
      .finally(() => setLoading(false));
  }, []);

  const groups: Record<string, ConfiguredTool[]> = { read: [], internal_write: [], external_write: [], exec: [], unclassified: [] };
  for (const t of tools) {
    const g = groups[t.risk] ? t.risk : "unclassified";
    groups[g].push(t);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">Tools</h2>
        <p className="text-text-muted text-xs">
          Tools the agent can call, grouped by risk class. Disable a tool here to remove it from the model entirely.
        </p>
      </div>

      {loading ? (
        <p className="text-text-muted text-xs">Loading…</p>
      ) : tools.length === 0 ? (
        <p className="text-text-muted text-xs">No tools registered.</p>
      ) : (
        Object.entries(groups).map(([risk, list]) =>
          list.length === 0 ? null : (
            <div key={risk}>
              <div className="flex items-center gap-2 mb-2">
                <span className={clsx("inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-medium", RISK_COLORS[risk] ?? "bg-elevated text-text-muted")}>
                  {risk === "exec" ? <Shield size={10} /> : <ShieldCheck size={10} />}
                  {risk}
                </span>
                <span className="text-text-muted text-2xs">{list.length} tool(s)</span>
              </div>
              <div className="bg-surface border border-rim rounded-xl overflow-hidden divide-y divide-rim">
                {list.map((t) => (
                  <div key={t.name} className="px-4 py-3 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-text-primary text-sm font-medium font-mono">{t.name}</p>
                      <p className="text-text-muted text-xs mt-0.5 line-clamp-2">{t.description}</p>
                    </div>
                    <span
                      className={clsx(
                        "text-2xs px-2 py-1 rounded flex-shrink-0",
                        t.enabled ? "bg-success/10 text-success" : "bg-ember/10 text-ember",
                      )}
                    >
                      {t.enabled ? "enabled" : "disabled"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ),
        )
      )}
    </div>
  );
}
