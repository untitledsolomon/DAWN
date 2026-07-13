"use client";

import React, { useEffect, useState } from "react";
import { RefreshCw, Database } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { getDataSourceHealth, type DataSourceHealth } from "@/lib/api";

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSourceHealth[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchSources();
  }, []);

  const fetchSources = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDataSourceHealth();
      setSources(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch data sources");
    } finally {
      setLoading(false);
    }
  };

  const getStatusDot = (status: string) => {
    switch (status) {
      case "live":
        return <span className="inline-block w-2 h-2 rounded-full bg-dawn" title="Live" />;
      case "empty":
        return <span className="inline-block w-2 h-2 rounded-full bg-amber-500" title="Empty" />;
      case "error":
        return <span className="inline-block w-2 h-2 rounded-full bg-red-500" title="Error" />;
      default:
        return <span className="inline-block w-2 h-2 rounded-full bg-text-muted" title="Unknown" />;
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);

    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin} min ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} hr ago`;
    return d.toLocaleDateString();
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Data Source Health</h1>
            <p className="text-text-muted text-2xs">Live status of every registered ontology object type</p>
          </div>
          <button
            onClick={fetchSources}
            disabled={loading}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {error && <p className="text-red-600 text-xs mb-3">{error}</p>}

          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : sources.length === 0 ? (
            <div className="bg-surface border border-rim rounded-xl p-8 text-center">
              <Database size={20} className="text-text-muted mx-auto mb-2" />
              <p className="text-text-muted text-xs">No object types registered yet.</p>
            </div>
          ) : (
            <div className="bg-surface border border-rim rounded-xl overflow-hidden max-w-4xl">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-elevated border-b border-rim">
                    <th className="text-left px-4 py-3 font-medium text-text-muted text-2xs uppercase tracking-wider">
                      Source
                    </th>
                    <th className="text-left px-4 py-3 font-medium text-text-muted text-2xs uppercase tracking-wider">
                      Status
                    </th>
                    <th className="text-left px-4 py-3 font-medium text-text-muted text-2xs uppercase tracking-wider">
                      Last Sync
                    </th>
                    <th className="text-right px-4 py-3 font-medium text-text-muted text-2xs uppercase tracking-wider">
                      Records
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rim">
                  {sources.map((source) => (
                    <tr key={source.table} className="hover:bg-elevated/50 transition-colors">
                      <td className="px-4 py-3">
                        <div className="text-text-primary font-medium">{source.name}</div>
                        <div className="text-text-muted text-2xs font-mono">{source.table}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {getStatusDot(source.status)}
                          <span className="text-text-secondary capitalize">{source.status}</span>
                        </div>
                        {source.error && <div className="text-red-600 text-2xs mt-0.5">{source.error}</div>}
                      </td>
                      <td className="px-4 py-3 text-text-secondary">{formatDate(source.last_sync)}</td>
                      <td className="px-4 py-3 text-right text-text-primary font-mono">
                        {source.record_count.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
