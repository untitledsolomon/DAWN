"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Search,
  Plus,
  Trash2,
  Globe,
  Mail,
  User,
  Building2,
  RefreshCw,
  ChevronDown,
  AlertTriangle,
  Info,
  Shield,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

interface OSINTTarget {
  id: string;
  target_type: string;
  value: string;
  label: string | null;
  tags: string[];
  notes: string | null;
  is_active: boolean;
  created_at: string;
}

interface OSINTResult {
  id: string;
  target_id: string;
  scan_type: string;
  summary: string | null;
  severity: string | null;
  findings_count: number;
  created_at: string;
}

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

const TYPE_ICONS: Record<string, React.ReactNode> = {
  domain: <Globe size={14} />,
  ip: <Shield size={14} />,
  email: <Mail size={14} />,
  username: <User size={14} />,
  organization: <Building2 size={14} />,
};

export default function OSINTPage() {
  const [targets, setTargets] = useState<OSINTTarget[]>([]);
  const [results, setResults] = useState<OSINTResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const [form, setForm] = useState({ target_type: "domain", value: "", label: "", tags: "", notes: "" });

  const loadData = useCallback(async () => {
    try {
      const [tRes, rRes] = await Promise.all([
        fetch(`${BASE}/osint/targets`, { headers: headers() }),
        fetch(`${BASE}/osint/results?limit=20`, { headers: headers() }),
      ]);
      if (tRes.ok) setTargets(await tRes.json());
      if (rRes.ok) setResults(await rRes.json());
    } catch (e) {
      console.error("Failed to load OSINT data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    try {
      const res = await fetch(`${BASE}/osint/targets`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          ...form,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        setShowForm(false);
        setForm({ target_type: "domain", value: "", label: "", tags: "", notes: "" });
        loadData();
      }
    } catch (e) {
      console.error("Failed to create target:", e);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this target and all its results?")) return;
    try {
      await fetch(`${BASE}/osint/targets/${id}`, { method: "DELETE", headers: headers() });
      setTargets((prev) => prev.filter((t) => t.id !== id));
    } catch (e) {
      console.error("Failed to delete target:", e);
    }
  };

  const getResultsForTarget = (targetId: string) => results.filter((r) => r.target_id === targetId);

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">OSINT Recon</h1>
            <p className="text-text-muted text-2xs">Open-source intelligence gathering</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all">
              <Plus size={12} /> Add Target
            </button>
            <button onClick={loadData} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {showForm && (
          <div className="border-b border-rim bg-elevated/30 px-6 py-4">
            <div className="max-w-xl space-y-3">
              <div>
                <label className="text-text-muted text-2xs font-medium block mb-1">Target Type</label>
                <div className="flex gap-2">
                  {["domain", "ip", "email", "username", "organization"].map((type) => (
                    <button key={type} onClick={() => setForm({ ...form, target_type: type })}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${form.target_type === type ? "bg-dawn/10 border-dawn/30 text-dawn" : "bg-surface border-rim text-text-muted"}`}>
                      {TYPE_ICONS[type]} {type}
                    </button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Value</label>
                  <input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs font-mono outline-none focus:border-dawn/50"
                    placeholder={form.target_type === "domain" ? "example.com" : form.target_type === "ip" ? "8.8.8.8" : "value"} />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Label</label>
                  <input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" />
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={handleCreate} disabled={!form.value}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30">
                  <Plus size={12} /> Add Target
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
          ) : targets.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <Search size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">No OSINT targets</p>
              <p className="text-text-muted text-xs">Add domains, IPs, or emails to start reconnaissance</p>
            </div>
          ) : (
            <div className="space-y-3 max-w-4xl">
              {targets.map((target) => {
                const targetResults = getResultsForTarget(target.id);
                const isExpanded = selectedTarget === target.id;
                return (
                  <div key={target.id} className="bg-surface border border-rim rounded-xl overflow-hidden hover:border-dawn/20 transition-all">
                    <button onClick={() => setSelectedTarget(isExpanded ? null : target.id)}
                      className="w-full text-left px-4 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-dawn/10 border border-dawn/20 flex items-center justify-center">
                          {TYPE_ICONS[target.target_type] || <Globe size={14} className="text-dawn" />}
                        </div>
                        <div>
                          <p className="text-text-primary text-sm font-medium">{target.label || target.value}</p>
                          <p className="text-text-muted text-xs font-mono">{target.value} · {target.target_type}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-text-muted text-2xs font-mono">{targetResults.length} scans</span>
                        <button onClick={(e) => { e.stopPropagation(); handleDelete(target.id); }}
                          className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-error hover:bg-error/10 transition-all">
                          <Trash2 size={10} />
                        </button>
                        <ChevronDown size={12} className={`text-text-muted transition-transform ${isExpanded ? "rotate-180" : ""}`} />
                      </div>
                    </button>
                    {isExpanded && targetResults.length > 0 && (
                      <div className="border-t border-rim px-4 py-3 bg-elevated/20 space-y-2">
                        {targetResults.map((result) => (
                          <div key={result.id} className="flex items-center justify-between py-1">
                            <div className="flex items-center gap-2">
                              <span className="px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono">{result.scan_type}</span>
                              {result.severity && (
                                <span className={`px-1.5 py-0.5 rounded text-2xs font-mono ${
                                  result.severity === "critical" ? "bg-error/10 text-error border border-error/20" :
                                  result.severity === "high" ? "bg-amber-500/10 text-amber-600 border border-amber-500/20" :
                                  "bg-dawn/5 text-dawn border border-dawn/15"
                                }`}>{result.severity}</span>
                              )}
                            </div>
                            <span className="text-text-muted text-2xs font-mono">{new Date(result.created_at).toLocaleString()}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {isExpanded && targetResults.length === 0 && (
                      <div className="border-t border-rim px-4 py-3 bg-elevated/20">
                        <p className="text-text-muted text-xs">No scan results yet. Use the OSINT tool in chat to scan this target.</p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
