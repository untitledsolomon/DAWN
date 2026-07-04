"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Terminal,
  Plus,
  Trash2,
  Server,
  Key,
  Check,
  X,
  RefreshCw,
  Globe,
  Lock,
  Activity,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

interface SSHHost {
  id: string;
  label: string;
  hostname: string;
  port: number;
  username: string;
  auth_method: string;
  tags: string[];
  notes: string | null;
  is_active: boolean;
  last_connected_at: string | null;
  created_at: string;
}

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

export default function SSHPage() {
  const [hosts, setHosts] = useState<SSHHost[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    label: "",
    hostname: "",
    port: 22,
    username: "root",
    auth_method: "key",
    encrypted_key: "",
    encrypted_password: "",
    tags: "",
    notes: "",
  });
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const loadHosts = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/ssh/hosts`, { headers: headers() });
      if (res.ok) {
        setHosts(await res.json());
      }
    } catch (e) {
      console.error("Failed to load SSH hosts:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadHosts(); }, [loadHosts]);

  const handleCreate = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${BASE}/ssh/hosts`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          ...form,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
          encrypted_key: form.auth_method === "key" ? form.encrypted_key : null,
          encrypted_password: form.auth_method === "password" ? form.encrypted_password : null,
        }),
      });
      if (res.ok) {
        setShowForm(false);
        setForm({ label: "", hostname: "", port: 22, username: "root", auth_method: "key", encrypted_key: "", encrypted_password: "", tags: "", notes: "" });
        loadHosts();
      }
    } catch (e) {
      console.error("Failed to create host:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this host?")) return;
    try {
      await fetch(`${BASE}/ssh/hosts/${id}`, { method: "DELETE", headers: headers() });
      setHosts((prev) => prev.filter((h) => h.id !== id));
    } catch (e) {
      console.error("Failed to delete host:", e);
    }
  };

  const handleTestConnection = async (host: SSHHost) => {
    setTestResult(`Testing connection to ${host.hostname}...`);
    try {
      const res = await fetch(`${BASE}/ssh/hosts/${host.id}`, { headers: headers() });
      if (res.ok) {
        setTestResult(`✅ Connected to ${host.hostname}:${host.port}`);
      }
    } catch {
      setTestResult(`❌ Failed to connect to ${host.hostname}`);
    }
    setTimeout(() => setTestResult(null), 3000);
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">SSH Hosts</h1>
            <p className="text-text-muted text-2xs">Manage remote server connections</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all"
            >
              <Plus size={12} />
              Add Host
            </button>
            <button onClick={loadHosts} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {testResult && (
          <div className="px-6 py-2 bg-dawn/5 border-b border-dawn/15 text-dawn text-xs font-mono">
            {testResult}
          </div>
        )}

        {showForm && (
          <div className="border-b border-rim bg-elevated/30 px-6 py-4">
            <div className="max-w-2xl space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Label</label>
                  <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" placeholder="Production DB Server" />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Hostname</label>
                  <input value={form.hostname} onChange={(e) => setForm({ ...form, hostname: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50" placeholder="192.168.1.100 or server.example.com" />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Port</label>
                  <input type="number" value={form.port} onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || 22 })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50" />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Username</label>
                  <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50" />
                </div>
              </div>
              <div>
                <label className="text-text-muted text-2xs font-medium block mb-1">Auth Method</label>
                <div className="flex gap-2">
                  <button onClick={() => setForm({ ...form, auth_method: "key" })}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${form.auth_method === "key" ? "bg-dawn/10 border-dawn/30 text-dawn" : "bg-surface border-rim text-text-muted"}`}>
                    <Key size={10} className="inline mr-1" /> SSH Key
                  </button>
                  <button onClick={() => setForm({ ...form, auth_method: "password" })}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${form.auth_method === "password" ? "bg-dawn/10 border-dawn/30 text-dawn" : "bg-surface border-rim text-text-muted"}`}>
                    <Lock size={10} className="inline mr-1" /> Password
                  </button>
                </div>
              </div>
              {form.auth_method === "key" ? (
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Private Key (PEM)</label>
                  <textarea value={form.encrypted_key} onChange={(e) => setForm({ ...form, encrypted_key: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50 h-20" placeholder="-----BEGIN RSA PRIVATE KEY-----..." />
                </div>
              ) : (
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Password</label>
                  <input type="password" value={form.encrypted_password} onChange={(e) => setForm({ ...form, encrypted_password: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50" />
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Tags (comma-separated)</label>
                  <input value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" placeholder="production, ubuntu, web" />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Notes</label>
                  <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" />
                </div>
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={handleCreate} disabled={saving || !form.label || !form.hostname}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30">
                  {saving ? <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <Plus size={12} />}
                  Save Host
                </button>
                <button onClick={() => setShowForm(false)}
                  className="px-4 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs font-medium transition-all">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : hosts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Server size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">No SSH hosts configured</p>
              <p className="text-text-muted text-xs">Add a host to start managing remote servers</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-w-4xl">
              {hosts.map((host) => (
                <div key={host.id} className="bg-surface border border-rim rounded-xl p-4 hover:border-dawn/20 transition-all group">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-lg bg-dawn/10 border border-dawn/20 flex items-center justify-center flex-shrink-0">
                        <Server size={16} className="text-dawn" />
                      </div>
                      <div>
                        <p className="text-text-primary text-sm font-medium">{host.label}</p>
                        <p className="text-text-muted text-xs font-mono mt-0.5">{host.username}@{host.hostname}:{host.port}</p>
                        <div className="flex items-center gap-2 mt-2">
                          {host.tags?.map((tag) => (
                            <span key={tag} className="px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono">{tag}</span>
                          ))}
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono ${host.auth_method === "key" ? "bg-dawn/5 text-dawn border border-dawn/15" : "bg-amber-500/5 text-amber-600 border border-amber-500/15"}`}>
                            {host.auth_method === "key" ? <Key size={8} /> : <Lock size={8} />}
                            {host.auth_method}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={() => handleTestConnection(host)}
                        className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
                        title="Test connection">
                        <Activity size={12} />
                      </button>
                      <button onClick={() => handleDelete(host.id)}
                        className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-error hover:bg-error/10 transition-all"
                        title="Delete">
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  {host.notes && (
                    <p className="text-text-muted text-2xs mt-2 pt-2 border-t border-rim">{host.notes}</p>
                  )}
                  {host.last_connected_at && (
                    <p className="text-text-muted text-2xs mt-1.5 font-mono">
                      Last connected: {new Date(host.last_connected_at).toLocaleString()}
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
