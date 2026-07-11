"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  BookOpen,
  Plus,
  Trash2,
  RefreshCw,
  Upload,
  Link,
  FileText,
  BookMarked,
  Lightbulb,
  ExternalLink,
  CheckCircle2,
  AlertCircle,
  Clock,
  Loader2,
  X,
  FileUp,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import {
  listBooks,
  addBook,
  deleteBook,
  ingestBook,
  ingestFile,
  ingestFiles,
  ingestUrl,
  getIngestionStatus,
  deleteIngestedDocument,
  type Book,
  type IngestFileResponse,
  type IngestJobStatus,
  type IngestBookResponse,
} from "@/lib/api";

const CATEGORIES = [
  "computer_science", "security", "business", "engineering", "mathematics",
  "artificial_intelligence", "networking", "economics", "design",
  "philosophy", "psychology", "history", "self_help", "biography",
];

const ACCEPTED_FORMATS = [
  ".pdf", ".epub", ".mobi", ".azw", ".azw3", ".fb2", ".djvu",
  ".docx", ".odt", ".pptx", ".odp", ".xlsx", ".xls", ".ods",
  ".md", ".markdown", ".html", ".htm", ".rtf", ".txt",
  ".csv", ".json", ".xml", ".yaml", ".yml", ".svg",
  ".tex", ".sty", ".cls", ".bib",
];

const FORMAT_LABELS: Record<string, string> = {
  pdf: "PDF", epub: "EPUB", mobi: "MOBI", azw: "AZW", azw3: "AZW3",
  fb2: "FB2", djvu: "DjVu",
  docx: "DOCX", odt: "ODT", pptx: "PPTX", odp: "ODP",
  xlsx: "XLSX", xls: "XLS", ods: "ODS",
  md: "Markdown", html: "HTML", rtf: "RTF", txt: "Text",
  csv: "CSV", json: "JSON", xml: "XML", yaml: "YAML", svg: "SVG",
  tex: "LaTeX",
};

interface UploadJob {
  jobId: string;
  title: string;
  filename: string;
  status: "queued" | "running" | "success" | "failed";
  error?: string;
  nodesCreated?: number;
}

export default function BooksPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", author: "", category: "computer_science", tags: "", notes: "" });

  // Upload state
  const [uploadMode, setUploadMode] = useState<"file" | "url" | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [urlInput, setUrlInput] = useState("");
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadJobs, setUploadJobs] = useState<UploadJob[]>([]);
  const [activeJobs, setActiveJobs] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await listBooks(filter || undefined);
      setBooks(data);
    } catch (e) {
      console.error("Failed to load books:", e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  // Poll active jobs
  useEffect(() => {
    if (activeJobs.size === 0) return;
    const interval = setInterval(async () => {
      let changed = false;
      const newActive = new Set(activeJobs);
      for (const jobId of activeJobs) {
        try {
          const status = await getIngestionStatus(jobId);
          setUploadJobs((prev) =>
            prev.map((j) =>
              j.jobId === jobId
                ? {
                    ...j,
                    status: status.status as UploadJob["status"],
                    error: status.error || undefined,
                    nodesCreated: status.result?.nodes_created,
                  }
                : j
            )
          );
          if (status.status === "success" || status.status === "failed") {
            newActive.delete(jobId);
            changed = true;
          }
        } catch {
          // Keep polling
        }
      }
      if (changed) {
        setActiveJobs(newActive);
        load(); // Refresh book list to update ingestion_status
      }
      if (newActive.size === 0) clearInterval(interval);
    }, 1500);
    return () => clearInterval(interval);
  }, [activeJobs, load]);

  const handleCreate = async () => {
    try {
      await addBook({
        ...form,
        tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
      });
      setShowForm(false);
      setForm({ title: "", author: "", category: "computer_science", tags: "", notes: "" });
      load();
    } catch (e) {
      console.error("Failed to add book:", e);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this book? This will also remove any ingested nodes.")) return;
    try {
      await deleteBook(id);
      setBooks((prev) => prev.filter((b) => b.id !== id));
    } catch (e) {
      console.error("Failed to delete book:", e);
    }
  };

  const handleIngestBook = async (book: Book) => {
    try {
      const result = await ingestBook(book.id);
      const job: UploadJob = {
        jobId: result.job_id,
        title: book.title,
        filename: `Book: ${book.title}`,
        status: "queued",
      };
      setUploadJobs((prev) => [job, ...prev]);
      setActiveJobs((prev) => new Set(prev).add(result.job_id));
    } catch (e: any) {
      console.error("Failed to queue book ingestion:", e);
    }
  };

  const handleFileUpload = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);

    if (selectedFiles.length === 1) {
      const file = selectedFiles[0];
      const title = uploadTitle || file.name.replace(/\.[^/.]+$/, "");
      const tags = uploadTags.split(",").map((t) => t.trim()).filter(Boolean);
      try {
        const result = await ingestFile(file, title, tags);
        const job: UploadJob = {
          jobId: result.job_id,
          title,
          filename: file.name,
          status: "queued",
        };
        setUploadJobs((prev) => [job, ...prev]);
        setActiveJobs((prev) => new Set(prev).add(result.job_id));
        resetUpload();
      } catch (e: any) {
        alert(`Upload failed: ${e.message}`);
      } finally {
        setUploading(false);
      }
      return;
    }

    // Multi-file path
    const tags = uploadTags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const result = await ingestFiles(selectedFiles, tags);
      const newJobs: UploadJob[] = result.jobs.map((j) => ({
        jobId: j.job_id,
        title: j.filename.replace(/\.[^/.]+$/, ""),
        filename: j.filename,
        status: "queued",
      }));
      setUploadJobs((prev) => [...newJobs, ...prev]);
      setActiveJobs((prev) => {
        const next = new Set(prev);
        newJobs.forEach((j) => next.add(j.jobId));
        return next;
      });
      if (result.errors > 0 && result.error_details) {
        const msg = result.error_details.map((e) => `${e.file}: ${e.error}`).join("\n");
        alert(`${result.queued} file(s) queued, ${result.errors} failed:\n${msg}`);
      }
      resetUpload();
    } catch (e: any) {
      alert(`Upload failed: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleUrlIngest = async () => {
    if (!urlInput.trim()) return;
    setUploading(true);
    const title = uploadTitle || urlInput.split("/").pop()?.split("?")[0] || "URL Document";
    const tags = uploadTags.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const result = await ingestUrl(urlInput.trim(), title, tags);
      const job: UploadJob = {
        jobId: result.job_id,
        title,
        filename: urlInput.trim(),
        status: "queued",
      };
      setUploadJobs((prev) => [job, ...prev]);
      setActiveJobs((prev) => new Set(prev).add(result.job_id));
      resetUpload();
    } catch (e: any) {
      alert(`URL ingestion failed: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const resetUpload = () => {
    setSelectedFiles([]);
    setUrlInput("");
    setUploadTitle("");
    setUploadTags("");
    setUploadMode(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    setSelectedFiles(files);
    if (files.length === 1 && !uploadTitle) {
      setUploadTitle(files[0].name.replace(/\.[^/.]+$/, ""));
    } else if (files.length > 1) {
      setUploadTitle(""); // Title is per-file for multi-upload, derived from filename
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success": return <CheckCircle2 size={12} className="text-success" />;
      case "failed": return <AlertCircle size={12} className="text-error" />;
      case "running": return <Loader2 size={12} className="text-dawn animate-spin" />;
      default: return <Clock size={12} className="text-text-muted" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "complete":
        return "bg-success/10 text-success border border-success/20";
      case "ingesting":
        return "bg-dawn/10 text-dawn border border-dawn/20";
      case "error":
        return "bg-error/10 text-error border border-error/20";
      default:
        return "bg-elevated/50 text-text-muted border border-rim";
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Library</h1>
            <p className="text-text-muted text-2xs">Books, documents, and knowledge gaps</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => { setShowForm(false); setUploadMode("file"); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all">
              <FileUp size={12} /> Upload
            </button>
            <button onClick={() => { setShowForm(false); setUploadMode("url"); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dawn/30 text-dawn hover:bg-dawn/10 text-xs font-medium transition-all">
              <Link size={12} /> From URL
            </button>
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-surface border border-rim text-text-secondary hover:text-dawn hover:border-dawn/30 text-xs font-medium transition-all">
              <Plus size={12} /> Add Book
            </button>
            <button onClick={load} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

        {/* Upload / URL Form */}
        {uploadMode && (
          <div className="border-b border-rim bg-elevated/30 px-6 py-4">
            <div className="max-w-xl space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-text-primary text-xs font-medium">
                  {uploadMode === "file" ? "Upload File" : "Ingest from URL"}
                </h3>
                <button onClick={resetUpload} className="text-text-muted hover:text-text-secondary">
                  <X size={14} />
                </button>
              </div>

              {uploadMode === "file" ? (
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">
                    File{selectedFiles.length > 1 ? "s" : ""}
                  </label>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={ACCEPTED_FORMATS.join(",")}
                    onChange={handleFileSelect}
                    className="w-full text-xs text-text-primary file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-dawn/10 file:text-dawn file:text-xs file:font-medium hover:file:bg-dawn/20"
                  />
                  {selectedFiles.length > 0 && (
                    <ul className="text-2xs text-text-muted mt-1 space-y-0.5 max-h-32 overflow-y-auto">
                      {selectedFiles.map((f, i) => (
                        <li key={i}>
                          {f.name} ({(f.size / 1e6).toFixed(1)} MB)
                        </li>
                      ))}
                    </ul>
                  )}
                  {selectedFiles.length > 1 && (
                    <p className="text-2xs text-text-muted mt-1">
                      Titles will be derived from filenames for multi-file uploads.
                    </p>
                  )}
                </div>
              ) : (
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">URL</label>
                  <input
                    value={urlInput}
                    onChange={(e) => setUrlInput(e.target.value)}
                    placeholder="https://example.com/book.epub"
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50 font-mono"
                  />
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                {selectedFiles.length <= 1 && (
                  <div>
                    <label className="text-text-muted text-2xs font-medium block mb-1">Title (optional)</label>
                    <input
                      value={uploadTitle}
                      onChange={(e) => setUploadTitle(e.target.value)}
                      placeholder="Auto from filename"
                      className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
                    />
                  </div>
                )}
                <div className={selectedFiles.length > 1 ? "col-span-2" : ""}>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Tags (comma-separated)</label>
                  <input
                    value={uploadTags}
                    onChange={(e) => setUploadTags(e.target.value)}
                    placeholder="e.g. philosophy, strategy"
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
                  />
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={uploadMode === "file" ? handleFileUpload : handleUrlIngest}
                  disabled={uploading || (uploadMode === "file" ? selectedFiles.length === 0 : !urlInput.trim())}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30"
                >
                  {uploading ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : uploadMode === "file" ? (
                    <Upload size={12} />
                  ) : (
                    <Link size={12} />
                  )}
                  {uploading
                    ? "Ingesting..."
                    : uploadMode === "file"
                    ? selectedFiles.length > 1
                      ? `Upload & Ingest ${selectedFiles.length} Files`
                      : "Upload & Ingest"
                    : "Ingest URL"}
                </button>
                <button onClick={resetUpload}
                  className="px-4 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs font-medium transition-all">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Book Form */}
        {showForm && (
          <div className="border-b border-rim bg-elevated/30 px-6 py-4">
            <div className="max-w-xl space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Title</label>
                  <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium block mb-1">Author</label>
                  <input value={form.author} onChange={(e) => setForm({ ...form, author: e.target.value })}
                    className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50" />
                </div>
              </div>
              <div>
                <label className="text-text-muted text-2xs font-medium block mb-1">Category</label>
                <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}
                  className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50">
                  {CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
                </select>
              </div>
              <div className="flex gap-2">
                <button onClick={handleCreate} disabled={!form.title}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30">
                  <Plus size={12} /> Add Book
                </button>
                <button onClick={() => setShowForm(false)}
                  className="px-4 py-2 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs font-medium transition-all">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : (
            <>
              {/* Active upload jobs */}
              {uploadJobs.length > 0 && (
                <div>
                  <h3 className="text-text-secondary text-xs font-medium uppercase tracking-wider mb-3 flex items-center gap-2">
                    <Clock size={12} /> Recent Ingestion Jobs
                  </h3>
                  <div className="space-y-2 max-w-4xl">
                    {uploadJobs.slice(0, 10).map((job) => (
                      <div key={job.jobId} className="bg-surface border border-rim rounded-xl px-4 py-3 flex items-center justify-between">
                        <div className="flex items-center gap-3 min-w-0">
                          {getStatusIcon(job.status)}
                          <div className="min-w-0">
                            <p className="text-text-primary text-sm font-medium truncate">{job.title}</p>
                            <p className="text-text-muted text-2xs truncate font-mono">{job.filename}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3 flex-shrink-0">
                          {job.status === "success" && job.nodesCreated !== undefined && (
                            <span className="text-2xs text-success font-mono">{job.nodesCreated} nodes</span>
                          )}
                          {job.status === "failed" && job.error && (
                            <span className="text-2xs text-error max-w-[200px] truncate" title={job.error}>{job.error}</span>
                          )}
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono ${
                            job.status === "success" ? "bg-success/10 text-success" :
                            job.status === "failed" ? "bg-error/10 text-error" :
                            job.status === "running" ? "bg-dawn/10 text-dawn" :
                            "bg-elevated/50 text-text-muted"
                          }`}>
                            {job.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Category filter */}
              <div className="flex gap-2 flex-wrap">
                <button onClick={() => setFilter(null)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${!filter ? "bg-dawn/10 border-dawn/30 text-dawn" : "bg-surface border-rim text-text-muted hover:text-text-secondary"}`}>
                  All
                </button>
                {CATEGORIES.map((cat) => (
                  <button key={cat} onClick={() => setFilter(cat)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${filter === cat ? "bg-dawn/10 border-dawn/30 text-dawn" : "bg-surface border-rim text-text-muted hover:text-text-secondary"}`}>
                    {cat.replace(/_/g, " ")}
                  </button>
                ))}
              </div>

              {/* Books */}
              {books.length > 0 && (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-w-5xl">
                  {books.map((book) => (
                    <div key={book.id} className="bg-surface border border-rim rounded-xl p-4 hover:border-dawn/20 transition-all group">
                      <div className="flex items-start justify-between">
                        <div className="flex items-start gap-3 min-w-0">
                          <div className="w-9 h-9 rounded-lg bg-dawn/10 border border-dawn/20 flex items-center justify-center flex-shrink-0">
                            <BookOpen size={16} className="text-dawn" />
                          </div>
                          <div className="min-w-0">
                            <p className="text-text-primary text-sm font-medium truncate">{book.title}</p>
                            {book.author && <p className="text-text-muted text-xs">{book.author}</p>}
                            {book.category && (
                              <span className="inline-block mt-1 px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono">
                                {book.category.replace(/_/g, " ")}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {!book.ingested && (
                            <button onClick={() => handleIngestBook(book)}
                              className="w-6 h-6 flex items-center justify-center rounded text-dawn hover:bg-dawn/10 transition-all" title="Ingest">
                              <RefreshCw size={10} />
                            </button>
                          )}
                          <button onClick={() => handleDelete(book.id)}
                            className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-error hover:bg-error/10 transition-all" title="Delete">
                            <Trash2 size={10} />
                          </button>
                        </div>
                      </div>
                      <div className="mt-2 flex items-center gap-2">
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono ${getStatusBadge(book.ingestion_status)}`}>
                          {book.ingestion_status === "complete" && <CheckCircle2 size={10} />}
                          {book.ingestion_status === "ingesting" && <Loader2 size={10} className="animate-spin" />}
                          {book.ingestion_status === "error" && <AlertCircle size={10} />}
                          {book.ingestion_status}
                        </span>
                        {book.ingested && (
                          <a href={`/books/${book.id}`}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono text-dawn hover:bg-dawn/10 transition-all">
                            <ExternalLink size={10} /> View
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {books.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 gap-3">
                  <BookMarked size={24} className="text-text-muted/30" />
                  <p className="text-text-muted text-sm">No books in the library</p>
                  <p className="text-text-muted text-xs">Upload a file, ingest from URL, or add a book to get started</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
