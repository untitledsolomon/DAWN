"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Puzzle,
  RefreshCw,
  CheckCircle,
  XCircle,
  KeyRound,
  Plus,
  Trash2,
  Copy,
  Check,
  Loader2,
  Lock,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { listSecrets, countSecrets, createSecret, deleteSecret } from "@/lib/api";
import type { SecretItem } from "@/lib/types";

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

type Tab = "integrations" | "secrets";

export default function IntegrationsPage() {
  const [tab, setTab] = useState<Tab>("integrations");

  // Integrations state
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState<string | null>(null);

  // Secrets state
  const [secrets, setSecrets] = useState<SecretItem[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(true);
  const [showAddSecret, setShowAddSecret] = useState(false);
  const [newName, setNewName] = useState("");
  const [newValue, setNewValue] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newTags, setNewTags] = useState("");
  const [revealed, setRevealed] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState<string | null>(null);
  const [secretError, setSecretError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

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

  const loadSecrets = useCallback(async () => {
    try {
      const [s] = await Promise.all([listSecrets()]);
      setSecrets(s);
    } catch (e) {
      console.error("Failed to load secrets:", e);
    } finally {
      setSecretsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "integrations") load();
 else loadSecrets();
  }, [tab, load, loadSecrets]);

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

  const handleAddSecret = async () => {
    if (!newName.trim() || !newValue.trim()) return;
    setAdding(true);
    setSecretError(null);
    try {
      const tags = newTags.split(",").map((t) => t.trim()).filter(Boolean);
      await createSecret({ name: newName.trim(), value: newValue, description: newDesc.trim() || undefined, tags });
      setNewName(""); setNewValue(""); setNewDesc(""); setNewTags("");
      setShowAddSecret(false);
      await loadSecrets();
    } catch (e) {
      console.error("Failed to add secret:", e);
      setSecretError("Failed to add secret");
    } finally {
      setAdding(false);
    }
  };

  const handleDeleteSecret = async (id: string) => {
    if (!confirm("Delete this secret?")) return;
    try {
      await deleteSecret(id);
      setSecrets((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      console.error("Failed to delete secret:", e);
    }
  };

  const handleCopy = (id: string, value: string) => {
    navigator.clipboard?.writeText(value).then(() => {
      setCopied(id);
      setTimeout(() => setCopied(null), 1500);
    });
  };

  const inputClass =
    "w-full bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all";

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Integrations</h1>
            <p className="text-text-muted text-2xs">Connect DAWN to services and manage API keys</p>
          </div>
          <button
            onClick={() => (tab === "integrations" ? load() : loadSecrets())}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
          >
            <RefreshCw size={14} className={(tab === "integrations" ? loading : secretsLoading) ? "animate-spin" : ""} />
          </button>
        </header>

        {/* Tabs */}
        <div className="flex items-center gap-1 px-6 py-2 border-b border-rim flex-shrink-0">
          {(
            [
              { id: "integrations" as Tab, label: "Services", icon: Puzzle },
              { id: "secrets" as Tab, label: "API Keys & Secrets", icon: KeyRound },
            ]
          ).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                tab === t.id ? "bg-dawn/10 text-dawn" : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <t.icon size={13} />
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {tab === "integrations" ? (
            loading ? (
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
            )
          ) : (
            <div className="max-w-3xl">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2 text-text-muted text-xs">
                  <Lock size={13} />
                  <span>Stored encrypted. DAWN can use these to call external APIs.</span>
                </div>
                <button
                  onClick={() => setShowAddSecret((v) => !v)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs font-medium hover:bg-dawn/20 transition-all"
                >
                  <Plus size={12} />
                  {showAddSecret ? "Close" : "Add Key"}
                </button>
              </div>

              {showAddSecret && (
                <div className="rounded-xl bg-surface border border-rim p-4 mb-4 space-y-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">Name</label>
                      <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="e.g. OpenAI API Key" className={inputClass} />
                    </div>
                    <div>
                      <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">Value / Key</label>
                      <input value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="sk-... or endpoint token" type="password" className={inputClass} />
                    </div>
                    <div>
                      <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">Description</label>
                      <input value={newDesc} onChange={(e) => setNewDesc(e.target.value)} placeholder="What is this used for?" className={inputClass} />
                    </div>
                    <div>
                      <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">Tags</label>
                      <input value={newTags} onChange={(e) => setNewTags(e.target.value)} placeholder="comma, separated" className={inputClass} />
                    </div>
                  </div>
                  {secretError && <p className="text-ember text-2xs">{secretError}</p>}
                  <div className="flex justify-end">
                    <button
                      onClick={handleAddSecret}
                      disabled={adding || !newName.trim() || !newValue.trim()}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all disabled:opacity-40"
                    >
                      {adding ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                      Save Key
                    </button>
                  </div>
                </div>
              )}

              {secretsLoading ? (
                <div className="flex items-center justify-center h-48">
                  <Loader2 size={18} className="text-dawn animate-spin" />
                </div>
              ) : secrets.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-2 py-16 rounded-xl border border-dashed border-rim">
                  <KeyRound size={24} className="text-text-muted/50" />
                  <p className="text-text-muted text-sm">No API keys yet. Add one to let DAWN call external services.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {secrets.map((secret) => (
                    <div key={secret.id} className="bg-surface border border-rim rounded-xl p-3 flex items-center justify-between group">
                      <div className="min-w-0">
                        <p className="text-text-primary text-xs font-medium truncate">{secret.name}</p>
                        {secret.description && <p className="text-text-muted text-2xs truncate">{secret.description}</p>}
                        {secret.tags && secret.tags.length > 0 && (
                          <div className="flex gap-1 mt-1 flex-wrap">
                            {secret.tags.map((t) => (
                              <span key={t} className="px-1.5 py-0.5 rounded bg-elevated/60 text-text-muted text-2xs">{t}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={() => handleCopy(secret.id, secret.name)}
                          className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
                          title="Copy name"
                        >
                          {copied === secret.id ? <Check size={12} className="text-dawn" /> : <Copy size={12} />}
                        </button>
                        <button
                          onClick={() => handleDeleteSecret(secret.id)}
                          className="w-7 h-7 flex items-center justify-center rounded text-text-muted opacity-0 group-hover:opacity-100 hover:text-ember transition-all"
                          title="Delete"
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
