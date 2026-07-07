"use client";

import React, { useEffect, useState } from "react";

interface DecisionLogEntry {
  id: string;
  workflow_name: string;
  triggered_by: string;
  llm_explanation: string;
  human_decision: string | null;
  human_decision_by: string | null;
  human_decision_at: string | null;
  override_reason: string | null;
  executed: boolean;
  created_at: string;
  ranked_options: any;
  constraint_results: any;
  recommended_option: any;
  input_snapshot: any;
  data_freshness: any;
}

export default function DecisionsPage() {
  const [entries, setEntries] = useState<DecisionLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    fetchDecisions();
  }, [filter]);

  const fetchDecisions = async () => {
    setLoading(true);
    try {
      let url = "/api/decision/log?limit=50";
      if (filter) url += `&decision=${filter}`;
      const resp = await fetch(url);
      const data = await resp.json();
      setEntries(data.data || []);
    } catch (err) {
      console.error("Failed to fetch decisions:", err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getDecisionBadge = (entry: DecisionLogEntry) => {
    if (!entry.human_decision) {
      return (
        <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400">
          Pending
        </span>
      );
    }
    switch (entry.human_decision) {
      case "approved":
        return (
          <span className="text-xs px-2 py-0.5 rounded bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400">
            ✓ Approved
          </span>
        );
      case "rejected":
        return (
          <span className="text-xs px-2 py-0.5 rounded bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400">
            ✗ Rejected
          </span>
        );
      case "overridden":
        return (
          <span className="text-xs px-2 py-0.5 rounded bg-yellow-100 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400">
            ⚠ Overridden
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Decision History</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-6">
        {[null, "approved", "rejected", "overridden"].map((f) => (
          <button
            key={f || "all"}
            onClick={() => setFilter(f)}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              filter === f
                ? "bg-blue-600 text-white"
                : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600"
            }`}
          >
            {f ? f.charAt(0).toUpperCase() + f.slice(1) : "All"}
          </button>
        ))}
      </div>

      {/* Decision List */}
      {loading ? (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">Loading...</div>
      ) : entries.length === 0 ? (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">
          No decisions recorded yet. Run a decision workflow to see results here.
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <div
              key={entry.id}
              className="border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 overflow-hidden"
            >
              {/* Summary row */}
              <div
                className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750"
                onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500 dark:text-gray-400 min-w-[100px]">
                    {formatDate(entry.created_at)}
                  </span>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">
                    {entry.workflow_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </span>
                  {getDecisionBadge(entry)}
                </div>
                <div className="flex items-center gap-2">
                  {entry.human_decision_by && (
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      by {entry.human_decision_by}
                    </span>
                  )}
                  <span className="text-gray-400 dark:text-gray-500 text-sm">
                    {expandedId === entry.id ? "▲" : "▼"}
                  </span>
                </div>
              </div>

              {/* Expanded trace */}
              {expandedId === entry.id && (
                <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
                  <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                    <div>
                      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                        Triggered By
                      </span>
                      <p className="text-gray-900 dark:text-white">{entry.triggered_by}</p>
                    </div>
                    <div>
                      <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                        Executed
                      </span>
                      <p className="text-gray-900 dark:text-white">
                        {entry.executed ? "Yes" : "No"}
                      </p>
                    </div>
                    {entry.human_decision_by && (
                      <div>
                        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                          Decision By
                        </span>
                        <p className="text-gray-900 dark:text-white">{entry.human_decision_by}</p>
                      </div>
                    )}
                    {entry.override_reason && (
                      <div className="col-span-2">
                        <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                          Override Reason
                        </span>
                        <p className="text-gray-900 dark:text-white">{entry.override_reason}</p>
                      </div>
                    )}
                  </div>

                  <div className="mb-4">
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                      DAWN&apos;s Explanation
                    </span>
                    <p className="text-sm text-gray-700 dark:text-gray-300 mt-1">
                      {entry.llm_explanation || "No explanation recorded"}
                    </p>
                  </div>

                  <div>
                    <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
                      Full Trace (JSON)
                    </span>
                    <pre className="mt-1 text-xs bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 overflow-auto max-h-60 text-gray-800 dark:text-gray-200">
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
  );
}
