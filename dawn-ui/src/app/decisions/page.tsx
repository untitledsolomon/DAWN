"use client";

import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, ScrollText } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { listDecisionLog, type DecisionLogEntry } from "@/lib/api";

const FILTERS: Array<{ label: string; value: string | null }> = [
  { label: "All", value: null },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
  { label: "Overridden", value: "overridden" },
];

export default function DecisionsPage() {
  const [entries, setEntries] = useState<DecisionLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    void fetchDecisions();
  }, [filter]);

  const fetchDecisions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDecisionLog({ limit: 50, decision: filter || undefined });
      setEntries(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch decisions");
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };

  const getDecisionBadge = (entry: DecisionLogEntry) => {
    if (!entry.human_decision) {
      return (
        <span className="text-2xs px-2 py-0.5 rounded font-mono bg-amber-500/10 text-amber-700 border border-amber-500/20">
          Pending
        </span>
      );
    }
    switch (entry.human_decision) {
      case "approved":
        return (
          <span className="text-2xs px-2 py-0.5 rounded font-mono bg-dawn/10 text-dawn border border-dawn/20">
            ✓ Approved
          </span>
        );
      case "rejected":
        return (
          <span className="text-2xs px-2 py-0.5 rounded font-mono bg-red-500/10 text-red-700 border border-red-500/20">
            ✗ Rejected
          </span>
        );
      case "overridden":
        return (
          <span className="text-2xs px-2 py-0.5 rounded font-mono bg-amber-500/10 text-amber-700 border border-amber-500/20">
            ⚠ Overridden
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Decision History</h1>
            <p className="text-text-muted text-2xs">Audit trail of every workflow run and its outcome</p>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4 max-w-6xl">
          {/* Filters */}
          <div className="flex flex-wrap gap-2 mb-4">
            {FILTERS.map((f) => (
              <button
                key={f.value || "all"}
                onClick={() => setFilter(f.value)}
                className={`px-3 py-1 text-2xs rounded-lg font-medium transition-all ${
                  filter === f.value
                    ? "bg-dawn/90 text-white"
                    : "bg-elevated text-text-secondary hover:bg-elevated/70 border border-rim"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {error && <p className="text-red-600 text-xs mb-3">{error}</p>}

          {/* Decision List */}
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : entries.length === 0 ? (
            <div className="bg-surface border border-rim rounded-xl p-8 text-center">
              <ScrollText size={20} className="text-text-muted mx-auto mb-2" />
              <p className="text-text-muted text-xs">No decisions recorded yet. Run a decision workflow to see results here.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {entries.map((entry) => (
                <div key={entry.id} className="bg-surface border border-rim rounded-xl overflow-hidden">
                  {/* Summary row */}
                  <div
                    className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-elevated/40 transition-colors"
                    onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-text-muted text-2xs min-w-[100px] font-mono">
                        {formatDate(entry.created_at)}
                      </span>
                      <span className="text-text-primary text-xs font-medium">
                        {entry.workflow_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                      </span>
                      {getDecisionBadge(entry)}
                    </div>
                    <div className="flex items-center gap-2">
                      {entry.human_decision_by && (
                        <span className="text-text-muted text-2xs">by {entry.human_decision_by}</span>
                      )}
                      {expandedId === entry.id ? (
                        <ChevronUp size={14} className="text-text-muted" />
                      ) : (
                        <ChevronDown size={14} className="text-text-muted" />
                      )}
                    </div>
                  </div>

                  {/* Expanded trace */}
                  {expandedId === entry.id && (
                    <div className="px-4 py-3 border-t border-rim bg-elevated/30">
                      <div className="grid grid-cols-2 gap-4 text-xs mb-4">
                        <div>
                          <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                            Triggered By
                          </span>
                          <p className="text-text-primary mt-0.5">{entry.triggered_by}</p>
                        </div>
                        <div>
                          <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                            Executed
                          </span>
                          <p className="text-text-primary mt-0.5">{entry.executed ? "Yes" : "No"}</p>
                        </div>
                        {entry.human_decision_by && (
                          <div>
                            <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                              Decision By
                            </span>
                            <p className="text-text-primary mt-0.5">{entry.human_decision_by}</p>
                          </div>
                        )}
                        {entry.override_reason && (
                          <div className="col-span-2">
                            <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                              Override Reason
                            </span>
                            <p className="text-text-primary mt-0.5">{entry.override_reason}</p>
                          </div>
                        )}
                      </div>

                      <div className="mb-4">
                        <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                          DAWN&apos;s Explanation
                        </span>
                        <p className="text-text-secondary text-xs mt-1 leading-relaxed">
                          {entry.llm_explanation || "No explanation recorded"}
                        </p>
                      </div>

                      <div>
                        <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">
                          Full Trace (JSON)
                        </span>
                        <pre className="mt-1 bg-surface border border-rim rounded-lg p-2 text-2xs font-mono overflow-auto max-h-60 text-text-secondary">
                          {JSON.stringify(
                            {
                              recommended: entry.recommended_option,
                              ranked_options: entry.ranked_options,
                              constraints: entry.constraint_results,
                              inputs: entry.input_snapshot,
                              freshness: entry.data_freshness,
                            },
                            null,
                            2
                          )}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
