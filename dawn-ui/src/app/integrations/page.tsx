"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Puzzle,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Settings,
  ExternalLink,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

interface Integration {
  id: string;
  service_name: string;
  display_name: string;
  description: string;
  is_connected: boolean;
  last_sync_at: string | null;
  sync_status: string;
  config: Record<string, unknown> | null;
}

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

const SERVICE_ICONS: Record<string, string> = {
  crm: "👥",
  pm: "📋",
  axis: "💰",
  forge: "🌐",
  sentinel: "🤖",
  nyaos: "⚡",
  econsim: "🏙️",
  mabruk: "👗",
  jarvis: "🧠",
};

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/integrations`, { headers: headers() });
      if (res.ok) setIntegrations(await res.json());
    } catch (e) {
      console.error("Failed to load integrations:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async (serviceName: string) => {
    setSyncing(serviceName);
    try {
      await fetch(`${BASE}/integrations/${serviceName}/sync`, { method: "POST", headers: headers() });
      load();
    } catch (e) {
      console.error("Failed to sync:", e);
    } finally {
      setSyncing(null);
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Integrations</h1>
            <p className="text-text-muted text-2xs">Connect DAWN to Regent's products and services</p>
          </div>
          <button onClick={load} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-w-5xl">
              {integrations.map((integration) => (
                <div key={integration.id} className="bg-surface border border-rim rounded-xl p-4 hover:border-dawn/20 transition-all group">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-elevated/50 border border-rim flex items-center justify-center text-lg">
                        {SERVICE_ICONS[integration.service_name] || "🔌"}
                      </div>
                      <div>
                        <p className="text-text-primary text-sm font-medium">{integration.display_name}</p>
                        <p className="text-text-muted text-2xs font-mono">{integration.service_name}</p>
                      </div>
                    </div>
                    <div className={`w-2 h-2 rounded-full mt-1.5 ${
                      integration.is_connected ? "bg-success" : "bg-text-muted/30"
                    }`} />
                  </div>
                  <p className="text-text-muted text-xs mb-3 line-clamp-2">{integration.description}</p>
                  <div className="flex items-center justify-between pt-2 border-t border-rim">
                    <div className="flex items-center gap-1.5">
                      {integration.is_connected ? (
                        <span className="flex items-center gap-1 text-success text-2xs font-mono">
                          <CheckCircle size={10} /> Connected
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-text-muted text-2xs font-mono">
                          <XCircle size={10} /> Disconnected
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => handleSync(integration.service_name)}
                      disabled={syncing === integration.service_name}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg text-dawn text-2xs font-medium hover:bg-dawn/10 transition-all disabled:opacity-30"
                    >
                      {syncing === integration.service_name ? (
                        <div className="w-3 h-3 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                      ) : (
                        <RefreshCw size={10} />
                      )}
                      Sync
                    </button>
                  </div>
                  {integration.last_sync_at && (
                    <p className="text-text-muted text-2xs mt-1.5 font-mono">
                      Last sync: {new Date(integration.last_sync_at).toLocaleString()}
                    </p>
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
