"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Activity,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Bell,
  Plus,
  Trash2,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

interface MonitorStatus {
  targets: {
    id: string;
    name: string;
    latest_check: {
      status: string;
      response_time_ms: number;
      checked_at: string;
    } | null;
  }[];
  summary: {
    total: number;
    up: number;
    down: number;
    healthy: boolean;
  };
}

interface AlertEvent {
  id: string;
  severity: string;
  title: string;
  message: string | null;
  acknowledged: boolean;
  created_at: string;
}

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

export default function MonitoringPage() {
  const [status, setStatus] = useState<MonitorStatus | null>(null);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [sRes, aRes] = await Promise.all([
        fetch(`${BASE}/monitor/status`, { headers: headers() }),
        fetch(`${BASE}/alerts/events?limit=20`, { headers: headers() }),
      ]);
      if (sRes.ok) setStatus(await sRes.json());
      if (aRes.ok) setAlerts(await aRes.json());
    } catch (e) {
      console.error("Failed to load monitoring data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAcknowledge = async (eventId: string) => {
    try {
      await fetch(`${BASE}/alerts/events/${eventId}/acknowledge`, { method: "POST", headers: headers() });
      setAlerts((prev) => prev.map((a) => a.id === eventId ? { ...a, acknowledged: true } : a));
    } catch (e) {
      console.error("Failed to acknowledge alert:", e);
    }
  };

  const timeAgo = (dateStr: string) => {
    const mins = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000 / 60);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Monitoring</h1>
            <p className="text-text-muted text-2xs">Infrastructure health and alerting</p>
          </div>
          <button onClick={load} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : (
            <>
              {/* Summary cards */}
              {status && (
                <div className="grid grid-cols-4 gap-3 max-w-4xl">
                  <div className="bg-surface border border-rim rounded-xl p-4">
                    <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Total</p>
                    <p className="text-text-primary text-2xl font-semibold mt-1">{status.summary.total}</p>
                  </div>
                  <div className="bg-surface border border-rim rounded-xl p-4">
                    <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Up</p>
                    <p className="text-success text-2xl font-semibold mt-1">{status.summary.up}</p>
                  </div>
                  <div className="bg-surface border border-rim rounded-xl p-4">
                    <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Down</p>
                    <p className="text-error text-2xl font-semibold mt-1">{status.summary.down}</p>
                  </div>
                  <div className={`border rounded-xl p-4 ${status.summary.healthy ? "bg-success/5 border-success/20" : "bg-error/5 border-error/20"}`}>
                    <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Status</p>
                    <p className={`text-lg font-semibold mt-1 ${status.summary.healthy ? "text-success" : "text-error"}`}>
                      {status.summary.healthy ? "Healthy" : "Issues"}
                    </p>
                  </div>
                </div>
              )}

              {/* Targets */}
              {status && status.targets.length > 0 && (
                <div className="max-w-4xl">
                  <h3 className="text-text-secondary text-xs font-medium uppercase tracking-wider mb-3">Services</h3>
                  <div className="space-y-2">
                    {status.targets.map((target) => (
                      <div key={target.id} className="bg-surface border border-rim rounded-xl px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className={`w-2 h-2 rounded-full ${
                            !target.latest_check ? "bg-text-muted/30" :
                            target.latest_check.status === "up" ? "bg-success" :
                            target.latest_check.status === "down" ? "bg-error" : "bg-amber-500"
                          }`} />
                          <span className="text-text-primary text-sm font-medium">{target.name}</span>
                        </div>
                        <div className="flex items-center gap-4">
                          {target.latest_check && (
                            <>
                              <span className="text-text-muted text-2xs font-mono">
                                {target.latest_check.response_time_ms}ms
                              </span>
                              <span className="text-text-muted text-2xs font-mono">
                                {timeAgo(target.latest_check.checked_at)}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Alerts */}
              {alerts.length > 0 && (
                <div className="max-w-4xl">
                  <h3 className="text-text-secondary text-xs font-medium uppercase tracking-wider mb-3">Recent Alerts</h3>
                  <div className="space-y-2">
                    {alerts.map((alert) => (
                      <div key={alert.id} className={`bg-surface border rounded-xl px-4 py-3 flex items-center justify-between ${
                        alert.acknowledged ? "border-rim opacity-60" : "border-rim hover:border-dawn/20"
                      }`}>
                        <div className="flex items-center gap-3">
                          <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${
                            alert.severity === "critical" ? "bg-error/10 border border-error/20" :
                            alert.severity === "warning" ? "bg-amber-500/10 border border-amber-500/20" :
                            "bg-dawn/10 border border-dawn/20"
                          }`}>
                            {alert.severity === "critical" ? <XCircle size={12} className="text-error" /> :
                             alert.severity === "warning" ? <AlertTriangle size={12} className="text-amber-600" /> :
                             <Bell size={12} className="text-dawn" />}
                          </div>
                          <div>
                            <p className="text-text-primary text-sm">{alert.title}</p>
                            {alert.message && <p className="text-text-muted text-xs">{alert.message}</p>}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-text-muted text-2xs font-mono">{timeAgo(alert.created_at)}</span>
                          {!alert.acknowledged && (
                            <button onClick={() => handleAcknowledge(alert.id)}
                              className="px-2 py-1 rounded text-2xs font-medium text-dawn hover:bg-dawn/10 transition-all">
                              Acknowledge
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(!status || status.targets.length === 0) && alerts.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 gap-3">
                  <Activity size={24} className="text-text-muted/30" />
                  <p className="text-text-muted text-sm">No monitoring data yet</p>
                  <p className="text-text-muted text-xs">Add monitoring targets to track infrastructure health</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
