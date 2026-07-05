"use client";

import { useState, useEffect, useCallback } from "react";
import {
  User,
  Crown,
  Cloud,
  HardDrive,
  Key,
  History,
  Palette,
  Bell,
  Shield,
  Server,
  Globe,
  Zap,
  Check,
  X,
  Trash2,
  RefreshCw,
  ChevronRight,
  Save,
  Eye,
  EyeOff,
  Moon,
  Sun,
  Monitor,
  Info,
  AlertTriangle,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { getSettings, updateSetting, getNotificationPrefs, updateNotificationPrefs, listSessions, deleteSession } from "@/lib/api";
import type { AppSettings, NotificationPrefs, ChatSession } from "@/lib/types";

type TabId = "general" | "model" | "api" | "history" | "appearance" | "notifications";

const TABS: { id: TabId; label: string; icon: React.ElementType; description: string }[] = [
  { id: "general", label: "General", icon: User, description: "Account, identity, and system information" },
  { id: "model", label: "Model", icon: Cloud, description: "Inference provider and model selection" },
  { id: "api", label: "API Keys", icon: Key, description: "Manage API keys for external services" },
  { id: "history", label: "History", icon: History, description: "Conversation history and data management" },
  { id: "appearance", label: "Appearance", icon: Palette, description: "Theme, font size, and display preferences" },
  { id: "notifications", label: "Notifications", icon: Bell, description: "Notification preferences and alerts" },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("general");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  // Settings state
  const [model, setModel] = useState<"deepseek" | "local">("deepseek");
  const [localEndpoint, setLocalEndpoint] = useState("http://localhost:11434");
  const [apiKey, setApiKey] = useState("");
  const [apiKeySaved, setApiKeySaved] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "system">("light");
  const [fontSize, setFontSize] = useState<"s" | "m" | "l">("m");

  // Notifications
  const [notifications, setNotifications] = useState<NotificationPrefs>({
    agent_complete: true,
    ingestion_finished: true,
    graph_updates: false,
    system_alerts: true,
  });

  // History
  const [conversations, setConversations] = useState<ChatSession[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Load settings from API
  const loadSettings = useCallback(async () => {
    setLoading(true);
    try {
      const [settings, prefs] = await Promise.all([
        getSettings().catch(() => null),
        getNotificationPrefs().catch(() => null),
      ]);

      if (settings) {
        if (settings.model) setModel(settings.model);
        if (settings.local_endpoint) setLocalEndpoint(settings.local_endpoint);
        if (settings.theme) setTheme(settings.theme);
        if (settings.font_size) setFontSize(settings.font_size);
        if (settings.deepseek_api_key) setApiKey(settings.deepseek_api_key);
      }

      if (prefs) {
        setNotifications({
          agent_complete: prefs.agent_complete ?? true,
          ingestion_finished: prefs.ingestion_finished ?? true,
          graph_updates: prefs.graph_updates ?? false,
          system_alerts: prefs.system_alerts ?? true,
        });
      }
    } catch (e) {
      console.error("[Settings] Failed to load:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  // Save a setting
  const saveSetting = async (key: string, value: unknown) => {
    setSaving(key);
    try {
      await updateSetting(key, value);
      await new Promise((r) => setTimeout(r, 300));
    } catch (e) {
      console.error(`[Settings] Failed to save ${key}:`, e);
    } finally {
      setSaving(null);
    }
  };

  const handleSaveKey = async () => {
    await saveSetting("deepseek_api_key", apiKey);
    setApiKeySaved(true);
    setTimeout(() => setApiKeySaved(false), 2000);
  };

  const handleModelChange = async (m: "deepseek" | "local") => {
    setModel(m);
    await saveSetting("model", m);
  };

  const handleThemeChange = async (t: "light" | "dark" | "system") => {
    setTheme(t);
    await saveSetting("theme", t);
  };

  const handleFontSizeChange = async (s: "s" | "m" | "l") => {
    setFontSize(s);
    await saveSetting("font_size", s);
  };

  const handleLocalEndpointSave = async () => {
    await saveSetting("local_endpoint", localEndpoint);
  };

  const toggleNotification = async (key: keyof NotificationPrefs) => {
    const newVal = !notifications[key];
    setNotifications((prev) => ({ ...prev, [key]: newVal }));
    await updateNotificationPrefs({ [key]: newVal });
  };

  // Load history
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const sessions = await listSessions();
      setConversations(sessions);
    } catch (e) {
      console.error("[Settings] Failed to load history:", e);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeTab === "history") loadHistory();
  }, [activeTab, loadHistory]);

  const handleDeleteSession = async (id: string) => {
    if (!confirm("Delete this conversation? This cannot be undone.")) return;
    try {
      await deleteSession(id);
      setConversations((prev) => prev.filter((s) => s.id !== id));
    } catch (e) {
      console.error("[Settings] Failed to delete session:", e);
    }
  };

  const handleClearAll = async () => {
    if (!confirm("Clear all conversation history? This cannot be undone.")) return;
    for (const conv of conversations) {
      try {
        await deleteSession(conv.id);
      } catch { /* skip */ }
    }
    setConversations([]);
  };

  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
  };

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-full">
          <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Page header */}
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="min-w-0">
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Settings</h1>
            <p className="text-text-muted text-2xs hidden sm:block">Configure DAWN to your preferences</p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className="inline-flex items-center gap-1 px-2 py-1 rounded-lg bg-dawn/10 border border-dawn/25 text-dawn text-2xs font-mono">
              <Zap size={10} />
              v3.0
            </span>
          </div>
        </header>

        <div className="flex flex-1 min-h-0 flex-col md:flex-row">
          {/* Tab nav — horizontal scrollable on mobile, sidebar on desktop */}
          <nav className="md:w-52 border-b md:border-b-0 md:border-r border-rim flex md:flex-col gap-0.5 p-2 md:p-3 flex-shrink-0 overflow-x-auto md:overflow-y-auto bg-surface/50">
            <p className="text-text-muted text-2xs font-medium uppercase tracking-wider px-2.5 pb-2 hidden md:block">Sections</p>
            {TABS.map(({ id, label, icon: Icon, description }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all text-left whitespace-nowrap md:whitespace-normal ${
                  activeTab === id
                    ? "bg-dawn/10 text-dawn font-medium"
                    : "text-text-muted hover:text-text-secondary hover:bg-elevated/40"
                }`}
              >
                <Icon size={16} strokeWidth={activeTab === id ? 2 : 1.75} className="flex-shrink-0" />
                <div className="min-w-0 flex-1 hidden md:block">
                  <span className="text-xs font-medium block truncate">{label}</span>
                  <span className="text-2xs text-text-muted/60 truncate block">{description}</span>
                </div>
                <span className="text-xs font-medium md:hidden">{label}</span>
                {activeTab === id && (
                  <ChevronRight size={12} className="text-dawn flex-shrink-0 hidden md:block" />
                )}
              </button>
            ))}
          </nav>

          {/* Content area */}
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-4 sm:px-8 py-4 sm:py-6">
              {/* General */}
              {activeTab === "general" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">General Settings</h2>
                    <p className="text-text-muted text-xs">Account information and system status</p>
                  </div>

                  {/* Identity card */}
                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">Identity</p>
                    </div>
                    <div className="p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Account</span>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-md bg-dawn/10 border border-dawn/20 flex items-center justify-center">
                            <User size={11} className="text-dawn" />
                          </div>
                          <span className="text-text-primary text-sm font-medium">Solomon John</span>
                        </div>
                      </div>
                      <div className="dawn-line" />
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Tier</span>
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-ember/10 text-ember text-xs font-mono font-medium">
                          <Crown size={10} strokeWidth={2.5} />
                          Owner
                        </span>
                      </div>
                      <div className="dawn-line" />
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Instance</span>
                        <span className="text-text-primary text-sm font-mono">Paperclip VPS</span>
                      </div>
                      <div className="dawn-line" />
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Region</span>
                        <span className="text-text-primary text-sm font-mono">Kampala, UG</span>
                      </div>
                    </div>
                  </div>

                  {/* About card */}
                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">About</p>
                    </div>
                    <div className="p-5 space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-dawn/10 border border-dawn/25 flex items-center justify-center">
                          <Zap size={18} className="text-dawn" />
                        </div>
                        <div>
                          <p className="text-text-primary text-base font-semibold tracking-tight">DAWN v3.0</p>
                          <p className="text-text-muted text-xs">Digital AI Working Network</p>
                        </div>
                      </div>
                      <p className="text-text-secondary text-sm leading-relaxed">
                        The internal knowledge layer and AI assistant for <strong className="text-text-primary">Regent</strong>, a digital systems and strategy firm based in Kampala, Uganda. DAWN powers knowledge retrieval, agent automation, and intelligent assistance across the organisation.
                      </p>
                      <div className="flex items-center gap-4 pt-1 flex-wrap">
                        <div className="flex items-center gap-1.5">
                          <Server size={12} className="text-text-muted" />
                          <span className="text-text-muted text-xs font-mono">Built by Solomon John</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Globe size={12} className="text-text-muted" />
                          <span className="text-text-muted text-xs font-mono">regent.ug</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* System status */}
                  <div className="bg-dawn/5 border border-dawn/15 rounded-xl p-4">
                    <div className="flex items-start gap-3">
                      <Shield size={16} className="text-dawn flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-text-primary text-sm font-medium">All systems operational</p>
                        <p className="text-text-muted text-xs mt-0.5">DAWN API · Knowledge Graph · Agent Runtime</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Model */}
              {activeTab === "model" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">Model Settings</h2>
                    <p className="text-text-muted text-xs">Choose your inference provider and model</p>
                  </div>

                  <div className="space-y-2">
                    <p className="text-text-secondary text-xs font-medium mb-1">Inference Provider</p>
                    <button
                      onClick={() => handleModelChange("deepseek")}
                      className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl border text-left transition-all ${
                        model === "deepseek"
                          ? "bg-dawn/8 border-dawn/30 text-dawn"
                          : "bg-surface border-rim text-text-secondary hover:border-dawn/20 hover:text-text-primary"
                      }`}
                    >
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                        model === "deepseek" ? "bg-dawn/15" : "bg-elevated/50 border border-rim"
                      }`}>
                        <Cloud size={18} strokeWidth={1.75} className={model === "deepseek" ? "text-dawn" : "text-text-muted"} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">DeepSeek</p>
                        <p className="text-xs text-text-muted mt-0.5">Remote · DeepSeek V3 / R1 · Recommended for complex reasoning</p>
                      </div>
                      {model === "deepseek" && <Check size={18} className="text-dawn flex-shrink-0" />}
                      {saving === "model" && (
                        <div className="w-4 h-4 border-2 border-rim border-t-dawn rounded-full animate-spin flex-shrink-0" />
                      )}
                    </button>
                    <button
                      onClick={() => handleModelChange("local")}
                      className={`w-full flex items-center gap-4 px-4 py-3.5 rounded-xl border text-left transition-all ${
                        model === "local"
                          ? "bg-dawn/8 border-dawn/30 text-dawn"
                          : "bg-surface border-rim text-text-secondary hover:border-dawn/20 hover:text-text-primary"
                      }`}
                    >
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                        model === "local" ? "bg-dawn/15" : "bg-elevated/50 border border-rim"
                      }`}>
                        <HardDrive size={18} strokeWidth={1.75} className={model === "local" ? "text-dawn" : "text-text-muted"} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium">Local</p>
                        <p className="text-xs text-text-muted mt-0.5">On-device · Ollama / LM Studio · No internet required</p>
                      </div>
                      {model === "local" && <Check size={18} className="text-dawn flex-shrink-0" />}
                      {saving === "model" && (
                        <div className="w-4 h-4 border-2 border-rim border-t-dawn rounded-full animate-spin flex-shrink-0" />
                      )}
                    </button>
                  </div>

                  {model === "local" && (
                    <div>
                      <label className="text-text-secondary text-xs font-medium block mb-1.5">Local Endpoint</label>
                      <div className="flex gap-2">
                        <input
                          value={localEndpoint}
                          onChange={(e) => setLocalEndpoint(e.target.value)}
                          className="flex-1 bg-surface border border-rim rounded-lg px-3 py-2.5 text-text-primary text-sm font-mono outline-none focus:border-dawn/50 transition-colors min-w-0"
                        />
                        <button
                          onClick={handleLocalEndpointSave}
                          className="flex items-center gap-1.5 px-3 py-2.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all flex-shrink-0"
                        >
                          {saving === "local_endpoint" ? (
                            <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          ) : (
                            <Save size={12} />
                          )}
                          Save
                        </button>
                      </div>
                      <p className="text-text-muted text-xs mt-1.5">Default: http://localhost:11434 (Ollama)</p>
                    </div>
                  )}

                  <div className="bg-amber-500/8 border border-amber-500/20 rounded-xl px-4 py-3 flex items-start gap-2.5">
                    <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
                    <p className="text-amber-700 text-xs leading-relaxed">
                      Model selection affects response quality and latency. DeepSeek is recommended for complex reasoning tasks. Local models may have reduced capability depending on hardware.
                    </p>
                  </div>
                </div>
              )}

              {/* API Keys */}
              {activeTab === "api" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">API Keys</h2>
                    <p className="text-text-muted text-xs">Manage API keys for external services</p>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">DeepSeek API Key</p>
                    </div>
                    <div className="p-5 space-y-3">
                      <div className="flex gap-2">
                        <div className="relative flex-1">
                          <input
                            type={showKey ? "text" : "password"}
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            placeholder="sk-..."
                            className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2.5 pr-10 text-text-primary text-sm font-mono placeholder:text-text-muted outline-none focus:border-dawn/50 transition-colors"
                          />
                          <button
                            onClick={() => setShowKey((p) => !p)}
                            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
                          >
                            {showKey ? <EyeOff size={14} /> : <Eye size={14} />}
                          </button>
                        </div>
                        <button
                          onClick={handleSaveKey}
                          disabled={!apiKey.trim()}
                          className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-medium transition-all flex-shrink-0 ${
                            apiKeySaved
                              ? "bg-success/10 text-success border border-success/20"
                              : "bg-dawn/90 hover:bg-dawn text-white disabled:opacity-30"
                          }`}
                        >
                          {apiKeySaved ? <><Check size={14} /> Saved</> : saving === "deepseek_api_key" ? (
                            <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          ) : "Save"}
                        </button>
                      </div>
                      <div className="flex items-center gap-2 text-text-muted text-xs">
                        <Info size={12} />
                        <span>Stored encrypted in the database. Used for DeepSeek API calls.</span>
                      </div>
                    </div>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">DAWN API</p>
                    </div>
                    <div className="p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Status</span>
                        <span className="inline-flex items-center gap-1.5 text-success text-sm font-medium">
                          <span className="w-2 h-2 rounded-full bg-success" />
                          Configured
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Endpoint</span>
                        <span className="text-text-primary text-sm font-mono truncate ml-2">{process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000"}</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-text-secondary text-sm">Version</span>
                        <span className="text-text-primary text-sm font-mono">v3.0.0</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* History */}
              {activeTab === "history" && (
                <div className="space-y-6">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">Conversation History</h2>
                      <p className="text-text-muted text-xs">Browse and manage your past conversations</p>
                    </div>
                    <button
                      onClick={handleClearAll}
                      disabled={conversations.length === 0}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-error/70 hover:text-error hover:bg-error/8 text-xs font-medium transition-all border border-transparent hover:border-error/20 disabled:opacity-30 flex-shrink-0"
                    >
                      <Trash2 size={12} />
                      <span className="hidden xs:inline">Clear all</span>
                    </button>
                  </div>

                  {historyLoading ? (
                    <div className="flex items-center justify-center py-16">
                      <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                    </div>
                  ) : conversations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16 gap-3 bg-surface border border-rim rounded-xl">
                      <History size={28} className="text-text-muted/30" />
                      <p className="text-text-muted text-sm">No conversation history</p>
                      <p className="text-text-muted text-xs">Start a conversation in Chat to see it here</p>
                    </div>
                  ) : (
                    <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                      <div className="divide-y divide-rim">
                        {conversations.map((conv) => (
                          <div
                            key={conv.id}
                            className="flex items-start justify-between px-5 py-4 hover:bg-elevated/30 transition-colors cursor-pointer group"
                          >
                            <div className="min-w-0 flex-1">
                              <p className="text-text-primary text-sm font-medium truncate">{conv.title}</p>
                              <div className="flex items-center gap-3 mt-1.5">
                                <span className="text-text-muted text-2xs">{conv.message_count} messages</span>
                                <span className="text-text-muted text-2xs font-mono">{timeAgo(conv.updated_at)}</span>
                              </div>
                            </div>
                            <button
                              onClick={() => handleDeleteSession(conv.id)}
                              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded text-text-muted hover:text-error hover:bg-error/8 flex-shrink-0"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        ))}
                      </div>
                      <div className="px-5 py-3 border-t border-rim bg-elevated/30 flex items-center justify-between">
                        <span className="text-text-muted text-xs">{conversations.length} conversations</span>
                        <button
                          onClick={loadHistory}
                          className="flex items-center gap-1 text-dawn text-xs hover:underline transition-colors"
                        >
                          <RefreshCw size={10} /> Refresh
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Appearance */}
              {activeTab === "appearance" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">Appearance</h2>
                    <p className="text-text-muted text-xs">Customise how DAWN looks</p>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">Theme</p>
                    </div>
                    <div className="p-5">
                      <div className="grid grid-cols-3 gap-2">
                        {([
                          { id: "light" as const, icon: Sun, label: "Light" },
                          { id: "dark" as const, icon: Moon, label: "Dark" },
                          { id: "system" as const, icon: Monitor, label: "System" },
                        ]).map(({ id, icon: Icon, label }) => (
                          <button
                            key={id}
                            onClick={() => handleThemeChange(id)}
                            className={`flex flex-col items-center gap-2 px-4 py-4 rounded-xl border transition-all ${
                              theme === id
                                ? "bg-dawn/8 border-dawn/30 text-dawn"
                                : "bg-elevated/30 border-rim text-text-muted hover:text-text-secondary hover:border-dawn/20"
                            }`}
                          >
                            <Icon size={20} strokeWidth={1.5} />
                            <span className="text-xs font-medium">{label}</span>
                            {theme === id && <Check size={12} className="text-dawn" />}
                            {saving === "theme" && (
                              <div className="w-3 h-3 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">Font Size</p>
                    </div>
                    <div className="p-5">
                      <div className="flex gap-2">
                        {([
                          { id: "s" as const, label: "S", desc: "Compact" },
                          { id: "m" as const, label: "M", desc: "Default" },
                          { id: "l" as const, label: "L", desc: "Large" },
                        ]).map(({ id, label, desc }) => (
                          <button
                            key={id}
                            onClick={() => handleFontSizeChange(id)}
                            className={`flex-1 flex flex-col items-center gap-1 px-4 py-3 rounded-xl border transition-all ${
                              fontSize === id
                                ? "bg-dawn/8 border-dawn/30 text-dawn"
                                : "bg-elevated/30 border-rim text-text-muted hover:text-text-secondary"
                            }`}
                          >
                            <span className="text-sm font-medium">{label}</span>
                            <span className="text-2xs text-text-muted">{desc}</span>
                            {saving === "font_size" && (
                              <div className="w-3 h-3 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">Preview</p>
                    </div>
                    <div className="p-5">
                      <div className="space-y-2">
                        <p className="text-text-primary text-sm font-medium">The quick brown fox jumps over the lazy dog</p>
                        <p className="text-text-secondary text-xs">DAWN responds with knowledge-grounded answers, tool calls, and agent traces — all rendered in your chosen font size.</p>
                        <code className="block text-xs font-mono bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-dawn">
                          {'const dawn = new DAWN({ theme: "' + theme + '", fontSize: "' + fontSize + '" });'}
                        </code>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Notifications */}
              {activeTab === "notifications" && (
                <div className="space-y-6">
                  <div>
                    <h2 className="text-text-primary text-base font-semibold tracking-tight mb-1">Notifications</h2>
                    <p className="text-text-muted text-xs">Control which events trigger notifications</p>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl overflow-hidden">
                    <div className="px-5 py-3 border-b border-rim bg-elevated/30">
                      <p className="text-text-secondary text-xs font-medium">Notification Preferences</p>
                    </div>
                    <div className="divide-y divide-rim">
                      {([
                        { key: "agent_complete" as const, label: "Agent task complete", desc: "When an agent finishes a multi-step task" },
                        { key: "ingestion_finished" as const, label: "Ingestion finished", desc: "When a file or repo finishes ingesting" },
                        { key: "graph_updates" as const, label: "Knowledge graph updates", desc: "When new nodes are auto-extracted" },
                        { key: "system_alerts" as const, label: "System alerts", desc: "API downtime, high latency, errors" },
                      ]).map(({ key, label, desc }) => (
                        <div key={key} className="flex items-center justify-between px-5 py-4 hover:bg-elevated/20 transition-colors gap-3">
                          <div className="min-w-0">
                            <p className="text-text-primary text-sm font-medium">{label}</p>
                            <p className="text-text-muted text-xs mt-0.5">{desc}</p>
                          </div>
                          <button
                            onClick={() => toggleNotification(key)}
                            className={`relative w-10 h-6 rounded-full transition-all flex-shrink-0 ${
                              notifications[key] ? "bg-dawn" : "bg-rim"
                            }`}
                          >
                            <div
                              className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-soft transition-all ${
                                notifications[key] ? "right-0.5" : "left-0.5"
                              }`}
                            />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="bg-surface border border-rim rounded-xl p-4">
                    <div className="flex items-start gap-3">
                      <Bell size={14} className="text-text-muted flex-shrink-0 mt-0.5" />
                      <div>
                        <p className="text-text-primary text-sm font-medium">Notification delivery</p>
                        <p className="text-text-muted text-xs mt-0.5">
                          Notifications appear in-app. Preferences are persisted to the database.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
