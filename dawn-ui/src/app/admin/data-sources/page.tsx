"use client";

import React, { useEffect, useState } from "react";

interface DataSource {
  name: string;
  table: string;
  status: string;
  record_count: number;
  last_sync: string | null;
  error?: string;
}

export default function DataSourcesPage() {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSources();
  }, []);

  const fetchSources = async () => {
    setLoading(true);
    try {
      const resp = await fetch("/api/admin/data-sources");
      const data = await resp.json();
      setSources(data.sources || []);
    } catch (err) {
      console.error("Failed to fetch data sources:", err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusDot = (status: string) => {
    switch (status) {
      case "live":
        return <span className="inline-block w-2 h-2 rounded-full bg-green-500" title="Live" />;
      case "empty":
        return <span className="inline-block w-2 h-2 rounded-full bg-yellow-500" title="Empty" />;
      case "error":
        return <span className="inline-block w-2 h-2 rounded-full bg-red-500" title="Error" />;
      default:
        return <span className="inline-block w-2 h-2 rounded-full bg-gray-400" title="Unknown" />;
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
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Data Source Health</h1>
        <button
          onClick={fetchSources}
          disabled={loading}
          className="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {loading ? (
        <div className="text-center text-gray-500 dark:text-gray-400 py-8">Loading...</div>
      ) : (
        <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 dark:bg-gray-900/50 border-b border-gray-200 dark:border-gray-700">
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">
                  Source
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">
                  Status
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">
                  Last Sync
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-500 dark:text-gray-400">
                  Records
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {sources.map((source) => (
                <tr key={source.table} className="hover:bg-gray-50 dark:hover:bg-gray-750">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900 dark:text-white">{source.name}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {source.table}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {getStatusDot(source.status)}
                      <span className="text-sm text-gray-700 dark:text-gray-300 capitalize">
                        {source.status}
                      </span>
                    </div>
                    {source.error && (
                      <div className="text-xs text-red-500 mt-0.5">{source.error}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">
                    {formatDate(source.last_sync)}
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-900 dark:text-white font-mono">
                    {source.record_count.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
