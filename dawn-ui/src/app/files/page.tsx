"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { listFiles, uploadFile, deleteArtifact, fileDownloadUrl } from "@/lib/api";
import type { FileArtifact } from "@/lib/api";
import {
  Upload,
  FileText,
  Download,
  Trash2,
  Loader2,
  AlertCircle,
  Clock,
  Tag,
  RefreshCw,
  X,
  CheckCircle2,
} from "lucide-react";
import clsx from "clsx";

function FilesContent() {
  const [files, setFiles] = useState<FileArtifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [tags, setTags] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listFiles();
      setFiles(data);
      setError(null);
    } catch (err) {
      console.error("[Files] Failed to load:", err);
      setError("Failed to load files");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelectedFile(file);
    if (file && !title) {
      setTitle(file.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const resetUpload = () => {
    setSelectedFile(null);
    setTitle("");
    setTags("");
    setUploadMsg(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    setUploadMsg(null);
    const tagList = tags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const result = await uploadFile(selectedFile, title || undefined, tagList);
      setUploadMsg({ kind: "success", text: `Uploaded "${result.title}" (${formatSize(result.size)})` });
      resetUpload();
      fetchFiles();
    } catch (err: any) {
      console.error("[Files] Upload failed:", err);
      setUploadMsg({ kind: "error", text: err?.message || "Upload failed" });
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this file?")) return;
    try {
      await deleteArtifact(id);
      setFiles((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      console.error("[Files] Failed to delete:", err);
    }
  };

  const formatSize = (bytes?: number | null) => {
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return `${Math.floor(days / 30)}mo ago`;
  };

  const filenameOf = (f: FileArtifact) => {
    if (f.url) {
      const seg = f.url.split("/").pop();
      if (seg) return decodeURIComponent(seg);
    }
    return f.title;
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-rim px-4 sm:px-6 py-3">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h1 className="text-text-primary text-sm font-semibold">Files</h1>
            <p className="text-text-muted text-2xs mt-0.5">
              Upload, manage, and download files
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-text-muted text-2xs font-mono">{files.length}</span>
            <button
              onClick={fetchFiles}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
              title="Refresh"
            >
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {/* Upload area */}
        <div className="bg-elevated/30 border border-rim rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-text-primary text-xs font-medium flex items-center gap-1.5">
              <Upload size={12} className="text-dawn" /> Upload File
            </h3>
            {selectedFile && (
              <button
                onClick={resetUpload}
                className="text-text-muted hover:text-text-secondary"
                title="Clear"
              >
                <X size={13} />
              </button>
            )}
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1">
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="w-full text-xs text-text-primary file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-dawn/10 file:text-dawn file:text-xs file:font-medium hover:file:bg-dawn/20"
              />
              {selectedFile && (
                <p className="text-2xs text-text-muted mt-1.5 flex items-center gap-1">
                  <FileText size={10} />
                  {selectedFile.name} ({formatSize(selectedFile.size)})
                </p>
              )}
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Title (optional)"
                className="w-full sm:w-48 bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
              />
              <input
                value={tags}
                onChange={(e) => setTags(e.target.value)}
                placeholder="Tags (comma-separated)"
                className="w-full sm:w-48 bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
              />
            </div>
            <button
              onClick={handleUpload}
              disabled={uploading || !selectedFile}
              className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30 flex-shrink-0"
            >
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {uploading ? "Uploading..." : "Upload"}
            </button>
          </div>

          {uploadMsg && (
            <div
              className={clsx(
                "mt-3 flex items-center gap-1.5 text-2xs",
                uploadMsg.kind === "success" ? "text-success" : "text-error"
              )}
            >
              {uploadMsg.kind === "success" ? (
                <CheckCircle2 size={11} />
              ) : (
                <AlertCircle size={11} />
              )}
              {uploadMsg.text}
            </div>
          )}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 size={20} className="text-dawn animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <AlertCircle size={18} className="text-error" />
            <p className="text-text-muted text-sm">{error}</p>
            <button
              onClick={fetchFiles}
              className="px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
            >
              Retry
            </button>
          </div>
        ) : files.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <FileText size={24} className="text-text-muted/50" />
            <p className="text-text-muted text-sm">No files yet. Upload one to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {files.map((file) => (
              <div
                key={file.id}
                className="p-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 transition-all group"
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="w-8 h-8 rounded-lg flex items-center justify-center border text-dawn bg-dawn/10 border-dawn/20">
                    <FileText size={14} />
                  </div>
                  <button
                    onClick={() => handleDelete(file.id)}
                    className="w-6 h-6 flex items-center justify-center rounded text-text-muted opacity-0 group-hover:opacity-100 hover:text-error transition-all"
                    title="Delete"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
                <h3 className="text-text-primary text-xs font-medium truncate" title={file.title}>
                  {file.title}
                </h3>
                <p className="text-text-muted text-2xs truncate font-mono mt-0.5" title={filenameOf(file)}>
                  {filenameOf(file)}
                </p>
                {file.description && (
                  <p className="text-text-muted text-2xs mt-1 line-clamp-2">{file.description}</p>
                )}
                <div className="flex items-center gap-2 mt-2">
                  <span className="flex items-center gap-1 text-text-muted text-2xs">
                    <Clock size={9} />
                    {timeAgo(file.created_at)}
                  </span>
                  {file.tags && file.tags.length > 0 && (
                    <span className="flex items-center gap-1 text-text-muted text-2xs">
                      <Tag size={9} />
                      {file.tags.length}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <a
                    href={fileDownloadUrl(file.id)}
                    download
                    className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-dawn/10 text-dawn text-2xs font-medium hover:bg-dawn/20 transition-all"
                  >
                    <Download size={10} /> Download
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function FilesPage() {
  return (
    <AppShell>
      <FilesContent />
    </AppShell>
  );
}
