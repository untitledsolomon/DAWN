"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { CheckCircle, XCircle, RefreshCw, Upload, FileText, GitBranch, FileUp } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import NodeCard from "@/components/nodes/NodeCard";
import {
  getPendingNodes, approveNode, rejectNode,
  getIngestionLog, ingestRepo, ingestDocument, ingestFile,
} from "@/lib/api";
import type { DawnNode, IngestionLog } from "@/lib/types";

const FILE_TYPE_MAP: Record<string, { label: string; color: string; bg: string; border: string; desc: string }> = {
  ".pdf":      { label: "PDF",      color: "text-orange-400", bg: "bg-orange-400/10", border: "border-orange-400/30", desc: "Text extracted page by page, chunked into nodes" },
  ".md":       { label: "Markdown", color: "text-blue-400",   bg: "bg-blue-400/10",   border: "border-blue-400/30",   desc: "Split on headings — each section becomes its own node" },
  ".markdown": { label: "Markdown", color: "text-blue-400",   bg: "bg-blue-400/10",   border: "border-blue-400/30",   desc: "Split on headings — each section becomes its own node" },
  ".csv":      { label: "CSV",      color: "text-green-400",  bg: "bg-green-400/10",  border: "border-green-400/30",  desc: "Each row becomes a fact node (max 500 rows)" },
  ".xlsx":     { label: "Excel",    color: "text-emerald-400",bg: "bg-emerald-400/10",border: "border-emerald-400/30",desc: "Each sheet gets a parent node, rows become child nodes" },
  ".xls":      { label: "Excel",    color: "text-emerald-400",bg: "bg-emerald-400/10",border: "border-emerald-400/30",desc: "Each sheet gets a parent node, rows become child nodes" },
  ".svg":      { label: "SVG",      color: "text-purple-400", bg: "bg-purple-400/10", border: "border-purple-400/30", desc: "Text labels, titles and descriptions extracted" },
};

const ACCEPT = Object.keys(FILE_TYPE_MAP).join(",");

function getFileExt(filename: string): string {
  return filename.slice(filename.lastIndexOf(".")).toLowerCase();
}

function detectType(filename: string) {
  return FILE_TYPE_MAP[getFileExt(filename)] ?? null;
}

export default function MemoryPage() {
  const [pending, setPending] = useState<DawnNode[]>([]);
  const [log, setLog] = useState<IngestionLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"review" | "upload" | "ingest" | "log">("review");

  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [fileTags, setFileTags] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [ingestType, setIngestType] = useState<"repo" | "document">("repo");
  const [repoPath, setRepoPath] = useState("");
  const [repoName, setRepoName] = useState("");
  const [docTitle, setDocTitle] = useState("");
  const [docContent, setDocContent] = useState("");
  const [ingestTags, setIngestTags] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [ingestMsg, setIngestMsg] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [p, l] = await Promise.all([getPendingNodes(), getIngestionLog()]);
      setPending(p);
      setLog(l);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (id: string) => {
    await approveNode(id);
    setPending((prev) => prev.filter((n) => n.id !== id));
  };

  const handleReject = async (id: string) => {
    await rejectNode(id);
    setPending((prev) => prev.filter((n) => n.id !== id));
  };

  const setFileAndTitle = (f: File) => {
    setFile(f);
    if (!fileTitle) setFileTitle(f.name.replace(/\.[^.]+$/, ""));
    setUploadMsg(null);
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && detectType(f.name)) setFileAndTitle(f);
    else setUploadMsg({ ok: false, text: "Unsupported file type. Supported: PDF, MD, CSV, XLSX, SVG" });
  };

  const handleFileUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadMsg(null);
    const tags = fileTags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const result = await ingestFile(file, fileTitle || file.name.replace(/\.[^.]+$/, ""), tags);
      const info = result.sections > 0
        ? `${result.sections} sections`
        : `${result.word_count?.toLocaleString() ?? "?"} words`;
      setUploadMsg({ ok: true, text: `✓ "${result.title}" queued — ${info} extracted as nodes` });
      setFile(null);
      setFileTitle("");
      setFileTags("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      setTimeout(load, 2000);
    } catch (e: unknown) {
      setUploadMsg({ ok: false, text: e instanceof Error ? e.message : "Upload failed" });
    } finally {
      setUploading(false);
    }
  };

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
      setTimeout(load, 2000);
    } catch {
      setIngestMsg("⚠️ Ingestion failed — check API logs");
    } finally {
      setIngesting(false);
    }
  };

  const detectedType = file ? detectType(file.name) : null;

  const TABS = [
    { id: "review" as const, label: "Pending Review", count: pending.length },
    { id: "upload" as const, label: "Upload File",    count: null },
    { id: "ingest" as const, label: "Ingest Data",    count: null },
    { id: "log" as const,    label: "Ingestion Log",  count: log.length },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="min-w-0">
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Memory</h1>
            <p className="text-text-muted text-2xs">Review auto-extracted facts · Upload files · Ingest data</p>
          </div>
          <button onClick={load} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all flex-shrink-0">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </header>

        {/* Tabs — scrollable on mobile */}
        <div className="flex border-b border-rim px-4 sm:px-6 flex-shrink-0 overflow-x-auto">
          {TABS.map(({ id, label, count }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`px-3 sm:px-4 py-2.5 text-xs font-medium border-b-2 transition-all -mb-px whitespace-nowrap ${
                tab === id ? "border-dawn text-dawn" : "border-transparent text-text-muted hover:text-text-secondary"
              }`}
            >
              {label}
              {count !== null && count > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-ember/20 text-ember text-2xs font-mono">{count}</span>
              )}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
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
                      <NodeCard key={node.id} node={node} showReviewActions onApprove={handleApprove} onReject={handleReject} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}

          {tab === "upload" && (
            <div className="max-w-lg space-y-5">
              <p className="text-text-secondary text-xs leading-relaxed">
                Drop any supported file — DAWN detects the type automatically and ingests it into the knowledge graph.
              </p>

              <div className="flex flex-wrap gap-2">
                {Object.entries(FILE_TYPE_MAP)
                  .filter(([ext]) => !ext.startsWith(".markdown") && ext !== ".xls")
                  .map(([ext, meta]) => (
                    <span key={ext} className={`text-2xs font-mono px-2 py-1 rounded-lg border ${meta.color} ${meta.bg} ${meta.border}`}>
                      {meta.label}
                    </span>
                  ))}
              </div>

              <div
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleFileDrop}
                className={`border-2 border-dashed rounded-xl px-4 sm:px-6 py-8 sm:py-10 text-center cursor-pointer transition-all ${
                  file && detectedType
                    ? `${detectedType.border.replace("border-", "border-")} ${detectedType.bg}`
                    : "border-rim hover:border-dawn/30 hover:bg-elevated/30"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) {
                      if (detectType(f.name)) setFileAndTitle(f);
                      else setUploadMsg({ ok: false, text: `Unsupported file type. Supported: PDF, MD, CSV, XLSX, SVG` });
                    }
                  }}
                />

                {file && detectedType ? (
                  <div className="flex flex-col items-center gap-3">
                    <FileText size={24} className={detectedType.color} />
                    <div className="text-center">
                      <p className="text-text-primary text-sm font-medium break-all">{file.name}</p>
                      <p className="text-text-muted text-xs mt-0.5">{(file.size / 1024).toFixed(0)} KB</p>
                    </div>
                    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-mono ${detectedType.color} ${detectedType.bg} ${detectedType.border}`}>
                      <span className="font-semibold">{detectedType.label} detected</span>
                      <span className="text-2xs opacity-70">·</span>
                      <span className="text-2xs opacity-70 hidden sm:inline">{detectedType.desc}</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); setFile(null); setFileTitle(""); setUploadMsg(null); }}
                      className="text-text-muted text-xs hover:text-ember transition-colors"
                    >
                      Remove file
                    </button>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <FileUp size={24} className="text-text-muted" />
                    <p className="text-text-secondary text-sm">Drop a file here or click to browse</p>
                    <p className="text-text-muted text-xs">PDF · MD · CSV · XLSX · SVG</p>
                  </div>
                )}
              </div>

              <div>
                <label className="text-text-secondary text-xs block mb-1.5">
                  Title <span className="text-text-muted">(auto-filled from filename)</span>
                </label>
                <input
                  value={fileTitle}
                  onChange={(e) => setFileTitle(e.target.value)}
                  placeholder="e.g. Tekowa Engineering Proposal"
                  className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 transition-colors"
                />
              </div>

              <div>
                <label className="text-text-secondary text-xs block mb-1.5">Tags (comma-separated)</label>
                <input
                  value={fileTags}
                  onChange={(e) => setFileTags(e.target.value)}
                  placeholder="client, regent, finance"
                  className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted font-mono outline-none focus:border-dawn/50 transition-colors"
                />
              </div>

              {uploadMsg && (
                <p className={`text-xs px-3 py-2 rounded-lg border ${
                  uploadMsg.ok
                    ? "text-success bg-success/10 border-success/20"
                    : "text-ember bg-ember/10 border-ember/20"
                }`}>
                  {uploadMsg.text}
                </p>
              )}

              <button
                onClick={handleFileUpload}
                disabled={!file || uploading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-dawn/90 hover:bg-dawn text-white text-sm font-medium disabled:opacity-40 transition-all w-full sm:w-auto justify-center"
              >
                <Upload size={14} />
                {uploading ? "Uploading..." : "Ingest File"}
              </button>
            </div>
          )}

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
