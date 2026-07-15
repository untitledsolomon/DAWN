"use client";

import { useState, useEffect, useCallback } from "react";
import {
  CheckCircle, XCircle, RefreshCw, Upload, FileText, GitBranch,
  Brain, Key, Database, Plus, Trash2, Eye, EyeOff, Copy,
  Check, X, Edit3, Shield, Lock,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import NodeCard from "@/components/nodes/NodeCard";
import {
  getPendingNodes, approveNode, rejectNode,
  getIngestionLog, ingestRepo, ingestDocument,
  listMemories, countMemories, createMemory, deleteMemory,
  approveMemory, rejectMemory,
  listSecrets, countSecrets, createSecret, getSecret, deleteSecret,
} from "@/lib/api";
import type { DawnNode, IngestionLog, MemoryItem, SecretItem, SecretWithValue } from "@/lib/types";

type TabId = "memories" | "secrets" | "review" | "ingest" | "log";

export default function MemoryPage() {
  // ── State ────────────────────────────────────────────────────────────────
  const [tab, setTab] = useState<TabId>("memories");

  // Knowledge graph state
  const [pending, setPending] = useState<DawnNode[]>([]);
  const [log, setLog] = useState<IngestionLog[]>([]);
  const [loading, setLoading] = useState(true);

  // Memories state
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [memoriesLoading, setMemoriesLoading] = useState(true);
  const [memoryCount, setMemoryCount] = useState(0);
  const [showAddMemory, setShowAddMemory] = useState(false);
  const [newMemoryTitle, setNewMemoryTitle] = useState("");
  const [newMemoryBody, setNewMemoryBody] = useState("");
  const [newMemoryType, setNewMemoryType] = useState("fact");
  const [newMemoryTags, setNewMemoryTags] = useState("");

  // Secrets state
  const [secrets, setSecrets] = useState<SecretItem[]>([]);
  const [secretsLoading, setSecretsLoading] = useState(true);
  const [secretCount, setSecretCount] = useState(0);
  const [showAddSecret, setShowAddSecret] = useState(false);
  const [newSecretName, setNewSecretName] = useState("");
  const [newSecretValue, setNewSecretValue] = useState("");
  const [newSecretDesc, setNewSecretDesc] = useState("");
  const [newSecretTags, setNewSecretTags] = useState("");
  const [revealedSecrets, setRevealedSecrets] = useState<Set<string>>(new Set());
  const [secretValues, setSecretValues] = useState<Map<string, string>>(new Map());
  const [copiedSecret, setCopiedSecret] = useState<string | null>(null);

  // Ingest state
  const [ingestType, setIngestType] = useState<"repo" | "document">("repo");
  const [repoPath, setRepoPath] = useState("");
  const [repoName, setRepoName] = useState("");
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");
  const [ingestTags, setIngestTags] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState("");

  // ── Load functions ───────────────────────────────────────────────────────

  const loadKnowledgeGraph = useCallback(async () => {
    setLoading(true);
    try {
      const [p, l] = await Promise.all([getPendingNodes(), getIngestionLog()]);
      setPending(p);
      setLog(l);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const loadMemories = useCallback(async () => {
    setMemoriesLoading(true);
    try {
      const [m, c] = await Promise.all([
        listMemories({ status: "all", limit: 100 }),
        countMemories("active"),
      ]);
      setMemories(m);
      setMemoryCount(c);
    } catch (e) { console.error(e); }
    finally { setMemoriesLoading(false); }
  }, []);

  const loadSecrets = useCallback(async () => {
    setSecretsLoading(true);
    try {
      const [s, c] = await Promise.all([listSecrets(), countSecrets()]);
      setSecrets(s);
      setSecretCount(c);
    } catch (e) { console.error(e); }
    finally { setSecretsLoading(false); }
  }, []);

  useEffect(() => {
    loadKnowledgeGraph();
    loadMemories();
    loadSecrets();
  }, [loadKnowledgeGraph, loadMemories, loadSecrets]);

  // ── Memory handlers ──────────────────────────────────────────────────────

  const handleAddMemory = async () => {
    if (!newMemoryTitle.trim()) return;
    try {
      const tags = newMemoryTags.split(",").map((t) => t.trim()).filter(Boolean);
      await createMemory({
        title: newMemoryTitle.trim(),
        body: newMemoryBody.trim() || undefined,
        fact_type: newMemoryType,
        tags,
      });
      setNewMemoryTitle("");
      setNewMemoryBody("");
      setNewMemoryTags("");
      setShowAddMemory(false);
      loadMemories();
    } catch (e) { console.error(e); }
  };

  const handleDeleteMemory = async (id: string) => {
    try {
      await deleteMemory(id);
      loadMemories();
    } catch (e) { console.error(e); }
  };

  const handleApproveMemory = async (id: string) => {
    try {
      await approveMemory(id);
      loadMemories();
    } catch (e) { console.error(e); }
  };

  const handleRejectMemory = async (id: string) => {
    try {
      await rejectMemory(id);
      loadMemories();
    } catch (e) { console.error(e); }
  };

  // ── Secret handlers ──────────────────────────────────────────────────────

  const handleAddSecret = async () => {
    if (!newSecretName.trim() || !newSecretValue.trim()) return;
    try {
      const tags = newSecretTags.split(",").map((t) => t.trim()).filter(Boolean);
      await createSecret({
        name: newSecretName.trim(),
        value: newSecretValue,
        description: newSecretDesc.trim() || undefined,
        tags,
      });
      setNewSecretName("");
      setNewSecretValue("");
      setNewSecretDesc("");
      setNewSecretTags("");
      setShowAddSecret(false);
      loadSecrets();
    } catch (e) { console.error(e); }
  };

  const handleRevealSecret = async (id: string) => {
    if (revealedSecrets.has(id)) {
      setRevealedSecrets((prev) => { const n = new Set(prev); n.delete(id); return n; });
      return;
    }
    try {
      const secret = await getSecret(id);
      setSecretValues((prev) => { const n = new Map(prev); n.set(id, secret.value); return n; });
      setRevealedSecrets((prev) => { const n = new Set(prev); n.add(id); return n; });
    } catch (e) { console.error(e); }
  };

  const handleCopySecret = async (id: string) => {
    const val = secretValues.get(id);
    if (!val) return;
    try {
      await navigator.clipboard.writeText(val);
      setCopiedSecret(id);
      setTimeout(() => setCopiedSecret(null), 2000);
    } catch { /* clipboard not available */ }
  };

  const handleDeleteSecret = async (id: string) => {
    try {
      await deleteSecret(id);
      loadSecrets();
    } catch (e) { console.error(e); }
  };

  // ── Ingest handlers ──────────────────────────────────────────────────────

  const handleIngest = async () => {
    setIngesting(true);
    setIngestMsg("");
    const tags = ingestTags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      if (ingestType === "repo") {
        await ingestRepo(repoPath, repoName, tags);
        setIngestMsg(`✓ Repo "${repoName}" queued for ingestion`);
      } else {
        await ingestDocument(docTitle, docContent, "", tags);
        setIngestMsg(`✓ Document "${docTitle}" queued for ingestion`);
      }
      setTimeout(loadKnowledgeGraph, 2000);
    } catch {
      setIngestMsg("⚠️ Ingestion failed — check API logs");
    } finally {
      setIngesting(false);
    }
  };

  // ── Tabs ─────────────────────────────────────────────────────────────────

  const TABS: { id: TabId; label: string; icon: React.ElementType; count?: number }[] = [
    { id: "memories", label: "Personal Memories", icon: Brain, count: memoryCount },
    { id: "secrets", label: "Secrets Vault", icon: Lock, count: secretCount },
    { id: "review", label: "Pending Review", icon: Database, count: pending.length },
    { id: "ingest", label: "Ingest Data", icon: Upload },
    { id: "log", label: "Ingestion Log", icon: FileText, count: log.length },
  ];

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="min-w-0">
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Memory</h1>
            <p className="text-text-muted text-2xs">Personal facts · Secrets vault · Knowledge graph</p>
          </div>
          <button onClick={() => { loadMemories(); loadSecrets(); loadKnowledgeGraph(); }}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all flex-shrink-0">
            <RefreshCw size={14} className={loading || memoriesLoading || secretsLoading ? "animate-spin" : ""} />
          </button>
        </header>

        <div className="flex border-b border-rim px-4 sm:px-6 flex-shrink-0 overflow-x-auto">
          {TABS.map(({ id, label, icon: Icon, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2.5 text-xs font-medium border-b-2 transition-all -mb-px whitespace-nowrap ${
                tab === id ? "border-dawn text-dawn" : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              <Icon size={13} />
              {label}
              {count !== undefined && count > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-ember/20 text-ember text-2xs font-mono">{count}</span>
              )}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
          {/* ════════════════════════════════════════════════════════════════
              TAB: Personal Memories
              ════════════════════════════════════════════════════════════════ */}
          {tab === "memories" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-text-secondary text-xs">
                  Facts DAWN remembers about you across conversations.
                </p>
                <button onClick={() => setShowAddMemory(!showAddMemory)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs font-medium hover:bg-dawn/20 transition-all">
                  <Plus size={13} /> Add Memory
                </button>
              </div>

              {showAddMemory && (
                <div className="bg-surface border border-rim rounded-xl p-4 space-y-3">
                  <div>
                    <label className="text-text-secondary text-xs block mb-1">Title</label>
                    <input value={newMemoryTitle} onChange={(e) => setNewMemoryTitle(e.target.value)}
                      placeholder="e.g. Home address"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                  </div>
                  <div>
                    <label className="text-text-secondary text-xs block mb-1">Body (optional)</label>
                    <textarea value={newMemoryBody} onChange={(e) => setNewMemoryBody(e.target.value)}
                      rows={2} placeholder="e.g. 48 Wavamunno Road, Kampala"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 resize-none" />
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-text-secondary text-xs block mb-1">Type</label>
                      <select value={newMemoryType} onChange={(e) => setNewMemoryType(e.target.value)}
                        className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm outline-none focus:border-dawn/50">
                        <option value="fact">Fact</option>
                        <option value="preference">Preference</option>
                        <option value="decision">Decision</option>
                        <option value="pattern">Pattern</option>
                      </select>
                    </div>
                    <div className="flex-1">
                      <label className="text-text-secondary text-xs block mb-1">Tags (comma-sep)</label>
                      <input value={newMemoryTags} onChange={(e) => setNewMemoryTags(e.target.value)}
                        placeholder="personal, address"
                        className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                    </div>
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button onClick={handleAddMemory}
                      disabled={!newMemoryTitle.trim()}
                      className="px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium disabled:opacity-40 transition-all">
                      Save Memory
                    </button>
                    <button onClick={() => setShowAddMemory(false)}
                      className="px-4 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs transition-all">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {memoriesLoading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                </div>
              ) : memories.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-2">
                  <Brain size={24} className="text-text-muted/50" />
                  <p className="text-text-muted text-sm">No memories yet</p>
                  <p className="text-text-muted text-2xs">Memories are created automatically during conversations, or you can add one manually.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {memories.map((mem) => (
                    <div key={mem.id}
                      className={`bg-surface border rounded-xl px-4 py-3 ${
                        mem.status === "active" ? "border-rim" :
                        mem.status === "draft" ? "border-amber/30" : "border-rim/50 opacity-60"
                      }`}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-medium ${
                              mem.status === "active" ? "text-text-primary" :
                              mem.status === "draft" ? "text-amber" : "text-text-muted"
                            }`}>{mem.title}</span>
                            <span className={`text-2xs font-mono px-1 py-0.5 rounded border ${
                              mem.status === "active" ? "text-success bg-success/10 border-success/20" :
                              mem.status === "draft" ? "text-amber bg-amber/10 border-amber/20" :
                              "text-text-muted bg-elevated/50 border-rim"
                            }`}>{mem.status}</span>
                            <span className="text-2xs font-mono text-text-muted px-1 py-0.5 rounded bg-elevated/30">{mem.fact_type}</span>
                            {mem.confidence >= 0.8 && (
                              <span className="text-2xs text-success">✓ high confidence</span>
                            )}
                          </div>
                          {mem.body && (
                            <p className="text-text-secondary text-xs mt-1">{mem.body}</p>
                          )}
                          {mem.tags && mem.tags.length > 0 && (
                            <div className="flex gap-1 mt-1.5 flex-wrap">
                              {mem.tags.map((tag) => (
                                <span key={tag} className="text-2xs font-mono px-1.5 py-0.5 rounded bg-elevated/50 text-text-muted border border-rim/50">{tag}</span>
                              ))}
                            </div>
                          )}
                          <p className="text-text-muted text-2xs mt-1.5 font-mono">
                            {new Date(mem.created_at).toLocaleDateString()} · {mem.source}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {mem.status === "draft" && (
                            <>
                              <button onClick={() => handleApproveMemory(mem.id)}
                                className="w-7 h-7 flex items-center justify-center rounded-lg text-success hover:bg-success/10 transition-all"
                                title="Approve">
                                <CheckCircle size={13} />
                              </button>
                              <button onClick={() => handleRejectMemory(mem.id)}
                                className="w-7 h-7 flex items-center justify-center rounded-lg text-ember hover:bg-ember/10 transition-all"
                                title="Reject">
                                <XCircle size={13} />
                              </button>
                            </>
                          )}
                          <button onClick={() => handleDeleteMemory(mem.id)}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-ember hover:bg-ember/10 transition-all"
                            title="Delete">
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              TAB: Secrets Vault
              ════════════════════════════════════════════════════════════════ */}
          {tab === "secrets" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-text-secondary text-xs">
                  Encrypted credentials DAWN can access at runtime. Values are encrypted at rest.
                </p>
                <button onClick={() => setShowAddSecret(!showAddSecret)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs font-medium hover:bg-dawn/20 transition-all">
                  <Plus size={13} /> Add Secret
                </button>
              </div>

              {showAddSecret && (
                <div className="bg-surface border border-rim rounded-xl p-4 space-y-3">
                  <div className="flex gap-3">
                    <div className="flex-1">
                      <label className="text-text-secondary text-xs block mb-1">Name</label>
                      <input value={newSecretName} onChange={(e) => setNewSecretName(e.target.value)}
                        placeholder="e.g. GITHUB_TOKEN"
                        className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 font-mono" />
                    </div>
                    <div className="flex-1">
                      <label className="text-text-secondary text-xs block mb-1">Tags (comma-sep)</label>
                      <input value={newSecretTags} onChange={(e) => setNewSecretTags(e.target.value)}
                        placeholder="github, auth"
                        className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                    </div>
                  </div>
                  <div>
                    <label className="text-text-secondary text-xs block mb-1">Value</label>
                    <textarea value={newSecretValue} onChange={(e) => setNewSecretValue(e.target.value)}
                      rows={2} placeholder="Paste your API key, token, or credential..."
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 resize-none font-mono" />
                  </div>
                  <div>
                    <label className="text-text-secondary text-xs block mb-1">Description (optional)</label>
                    <input value={newSecretDesc} onChange={(e) => setNewSecretDesc(e.target.value)}
                      placeholder="e.g. GitHub personal access token for repo operations"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button onClick={handleAddSecret}
                      disabled={!newSecretName.trim() || !newSecretValue.trim()}
                      className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium disabled:opacity-40 transition-all">
                      <Lock size={12} /> Encrypt & Save
                    </button>
                    <button onClick={() => setShowAddSecret(false)}
                      className="px-4 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs transition-all">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {secretsLoading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                </div>
              ) : secrets.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-2">
                  <Shield size={24} className="text-text-muted/50" />
                  <p className="text-text-muted text-sm">No secrets stored</p>
                  <p className="text-text-muted text-2xs">Store API keys, tokens, and credentials here instead of the sandbox.</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {secrets.map((sec) => (
                    <div key={sec.id}
                      className="bg-surface border border-rim rounded-xl px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <Lock size={12} className="text-dawn" />
                            <span className="text-text-primary text-xs font-medium font-mono">{sec.name}</span>
                            {sec.tags && sec.tags.length > 0 && sec.tags.map((tag) => (
                              <span key={tag} className="text-2xs font-mono px-1.5 py-0.5 rounded bg-elevated/50 text-text-muted border border-rim/50">{tag}</span>
                            ))}
                          </div>
                          {sec.description && (
                            <p className="text-text-muted text-2xs mt-1">{sec.description}</p>
                          )}
                          {revealedSecrets.has(sec.id) && (
                            <div className="mt-2 flex items-center gap-2">
                              <code className="flex-1 bg-elevated/80 border border-rim rounded-lg px-3 py-2 text-xs font-mono text-text-primary break-all select-all">
                                {secretValues.get(sec.id)}
                              </code>
                              <button onClick={() => handleCopySecret(sec.id)}
                                className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
                                title="Copy">
                                {copiedSecret === sec.id ? <Check size={12} className="text-success" /> : <Copy size={12} />}
                              </button>
                            </div>
                          )}
                          <p className="text-text-muted text-2xs mt-1.5 font-mono">
                            Created {new Date(sec.created_at).toLocaleDateString()}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          <button onClick={() => handleRevealSecret(sec.id)}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
                            title={revealedSecrets.has(sec.id) ? "Hide" : "Reveal"}>
                            {revealedSecrets.has(sec.id) ? <EyeOff size={12} /> : <Eye size={12} />}
                          </button>
                          <button onClick={() => handleDeleteSecret(sec.id)}
                            className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-ember hover:bg-ember/10 transition-all"
                            title="Delete">
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              TAB: Pending Review (knowledge graph nodes)
              ════════════════════════════════════════════════════════════════ */}
          {tab === "review" && (
            <>
              {loading ? (
                <div className="flex items-center justify-center h-48">
                  <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
                </div>
              ) : pending.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 gap-2">
                  <CheckCircle size={24} className="text-success/50" />
                  <p className="text-text-muted text-sm">All caught up — no pending nodes</p>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-text-secondary text-xs mb-4">
                    These facts were auto-extracted from conversations. Approve to add to the knowledge graph, reject to discard.
                  </p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {pending.map((node) => (
                      <NodeCard key={node.id} node={node} showReviewActions
                        onApprove={(id: string) => { approveNode(id); setPending((prev) => prev.filter((n) => n.id !== id)); }}
                        onReject={(id: string) => { rejectNode(id); setPending((prev) => prev.filter((n) => n.id !== id)); }} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* ════════════════════════════════════════════════════════════════
              TAB: Ingest Data
              ════════════════════════════════════════════════════════════════ */}
          {tab === "ingest" && (
            <div className="max-w-lg space-y-6">
              <div className="flex gap-2">
                {(["repo", "document"] as const).map((t) => (
                  <button
                    key={t}
                    onClick={() => setIngestType(t)}
                    className={`flex items-center gap-2 px-4 py-2.5 rounded-xl border text-sm transition-all flex-1 sm:flex-none justify-center ${
                      ingestType === t
                        ? "bg-dawn/10 border-dawn/40 text-dawn"
                        : "bg-surface border-rim text-text-muted hover:text-text-secondary"
                    }`}
                  >
                    {t === "repo" ? <GitBranch size={14} /> : <FileText size={14} />}
                    {t === "repo" ? "Git Repository" : "Paste Text"}
                  </button>
                ))}
              </div>

              {ingestType === "repo" ? (
                <div className="space-y-3">
                  <div>
                    <label className="text-text-secondary text-xs block mb-1.5">Repo path (absolute, on the server)</label>
                    <input value={repoPath} onChange={(e) => setRepoPath(e.target.value)}
                      placeholder="/home/solomon/projects/sentinel"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted font-mono outline-none focus:border-dawn/50" />
                  </div>
                  <div>
                    <label className="text-text-secondary text-xs block mb-1.5">Repo name</label>
                    <input value={repoName} onChange={(e) => setRepoName(e.target.value)}
                      placeholder="Sentinel Trading Bot"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="text-text-secondary text-xs block mb-1.5">Title</label>
                    <input value={docTitle} onChange={(e) => setDocTitle(e.target.value)}
                      placeholder="e.g. Meeting notes — Tekowa kickoff"
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50" />
                  </div>
                  <div>
                    <label className="text-text-secondary text-xs block mb-1.5">Content</label>
                    <textarea value={docContent} onChange={(e) => setDocContent(e.target.value)}
                      rows={8} placeholder="Paste text here..."
                      className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 resize-none" />
                  </div>
                </div>
              )}

              <div>
                <label className="text-text-secondary text-xs block mb-1.5">Tags (comma-separated)</label>
                <input value={ingestTags} onChange={(e) => setIngestTags(e.target.value)}
                  placeholder="trading, regent, infrastructure"
                  className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted font-mono outline-none focus:border-dawn/50" />
              </div>

              {ingestMsg && (
                <p className={`text-xs px-3 py-2 rounded-lg border ${
                  ingestMsg.startsWith("✓")
                    ? "text-success bg-success/10 border-success/20"
                    : "text-ember bg-ember/10 border-ember/20"
                }`}>{ingestMsg}</p>
              )}

              <button
                onClick={handleIngest}
                disabled={ingesting || (ingestType === "repo" ? !repoPath || !repoName : !docTitle || !docContent)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-dawn/90 hover:bg-dawn text-white text-sm font-medium disabled:opacity-40 transition-all w-full sm:w-auto justify-center"
              >
                <Upload size={14} />
                {ingesting ? "Queuing..." : "Start Ingestion"}
              </button>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              TAB: Ingestion Log
              ════════════════════════════════════════════════════════════════ */}
          {tab === "log" && (
            <div className="space-y-2">
              {log.length === 0 ? (
                <p className="text-text-muted text-sm text-center py-12">No ingestion history yet</p>
              ) : (
                log.map((entry) => (
                  <div key={entry.id} className={`bg-surface border rounded-xl px-4 py-3 ${entry.status === "success" ? "border-rim" : "border-ember/30"}`}>
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={`text-2xs font-mono px-1.5 py-0.5 rounded border flex-shrink-0 ${
                          entry.status === "success"
                            ? "text-success bg-success/10 border-success/20"
                            : "text-ember bg-ember/10 border-ember/20"
                        }`}>{entry.status}</span>
                        <span className="text-text-secondary text-xs font-mono truncate">{entry.source}</span>
                      </div>
                      <span className="text-text-muted text-2xs font-mono flex-shrink-0">{new Date(entry.ingested_at).toLocaleString()}</span>
                    </div>
                    <p className="text-text-muted text-xs font-mono mt-1 truncate">{entry.source_ref}</p>
                    {entry.status === "success" && (
                      <p className="text-text-secondary text-2xs mt-1">{entry.nodes_created} nodes · {entry.edges_created || 0} edges</p>
                    )}
                    {entry.error && <p className="text-ember text-2xs mt-1 font-mono">{entry.error}</p>}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
