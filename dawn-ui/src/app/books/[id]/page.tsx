"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  BookOpen,
  FileText,
  Tag,
  Calendar,
  User,
  Layers,
  ExternalLink,
  Trash2,
  RefreshCw,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Clock,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { getBook, getIngestedDocument, deleteBook, deleteIngestedDocument, type Book } from "@/lib/api";

interface IngestedDoc {
  id: string;
  title: string;
  type: string;
  body?: string;
  status: string;
  source: string;
  source_ref?: string;
  tags?: string[];
  created_at: string;
  updated_at: string;
}

export default function BookDetailPage() {
  const params = useParams();
  const router = useRouter();
  const bookId = params.id as string;

  const [book, setBook] = useState<Book | null>(null);
  const [doc, setDoc] = useState<IngestedDoc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const b = await getBook(bookId);
        setBook(b);

        // Try to find the ingested document node
        if (b.ingested) {
          try {
            // The ingested doc might have the same ID or we search by title
            const d = await getIngestedDocument(bookId);
            setDoc(d);
          } catch {
            // Document node not found by ID — that's fine
          }
        }
      } catch (e: any) {
        setError(e.message || "Failed to load book");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [bookId]);

  const handleDelete = async () => {
    if (!confirm("Delete this book and its ingested content?")) return;
    setDeleting(true);
    try {
      // Delete ingested doc first if it exists
      if (doc) {
        try { await deleteIngestedDocument(doc.id); } catch {}
      }
      await deleteBook(bookId);
      router.push("/books");
    } catch (e: any) {
      alert(`Failed to delete: ${e.message}`);
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch {
      return dateStr;
    }
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

  if (error || !book) {
    return (
      <AppShell>
        <div className="flex flex-col items-center justify-center h-full gap-3">
          <AlertCircle size={24} className="text-error" />
          <p className="text-text-primary text-sm">{error || "Book not found"}</p>
          <button onClick={() => router.push("/books")}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all">
            <ArrowLeft size={12} /> Back to Library
          </button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="flex items-center gap-3">
            <button onClick={() => router.push("/books")}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <ArrowLeft size={14} />
            </button>
            <div>
              <h1 className="text-text-primary font-semibold text-sm tracking-tight">{book.title}</h1>
              <p className="text-text-muted text-2xs">Book details & ingested content</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={handleDelete} disabled={deleting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-error/30 text-error hover:bg-error/10 text-xs font-medium transition-all disabled:opacity-30">
              {deleting ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
              Delete
            </button>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Metadata card */}
          <div className="bg-surface border border-rim rounded-xl p-5 max-w-3xl">
            <div className="flex items-start gap-4">
              <div className="w-12 h-12 rounded-xl bg-dawn/10 border border-dawn/20 flex items-center justify-center flex-shrink-0">
                <BookOpen size={22} className="text-dawn" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-text-primary text-base font-semibold">{book.title}</h2>
                {book.author && (
                  <p className="text-text-muted text-sm flex items-center gap-1.5 mt-1">
                    <User size={12} /> {book.author}
                  </p>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
              <div>
                <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Category</p>
                <p className="text-text-primary text-xs font-mono mt-1">
                  {book.category ? book.category.replace(/_/g, " ") : "—"}
                </p>
              </div>
              <div>
                <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Status</p>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-2xs font-mono mt-1 ${
                  book.ingestion_status === "complete" ? "bg-success/10 text-success border border-success/20" :
                  book.ingestion_status === "ingesting" ? "bg-dawn/10 text-dawn border border-dawn/20" :
                  book.ingestion_status === "error" ? "bg-error/10 text-error border border-error/20" :
                  "bg-elevated/50 text-text-muted border border-rim"
                }`}>
                  {book.ingestion_status === "complete" && <CheckCircle2 size={10} />}
                  {book.ingestion_status === "ingesting" && <Loader2 size={10} className="animate-spin" />}
                  {book.ingestion_status === "error" && <AlertCircle size={10} />}
                  {book.ingestion_status}
                </span>
              </div>
              <div>
                <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Created</p>
                <p className="text-text-primary text-xs mt-1 flex items-center gap-1">
                  <Calendar size={10} /> {formatDate(book.created_at)}
                </p>
              </div>
              <div>
                <p className="text-text-muted text-2xs font-medium uppercase tracking-wider">Tags</p>
                <div className="flex gap-1 flex-wrap mt-1">
                  {book.tags.length > 0 ? book.tags.map((t) => (
                    <span key={t} className="px-1.5 py-0.5 rounded bg-elevated/50 border border-rim text-text-muted text-2xs font-mono">
                      {t}
                    </span>
                  )) : <span className="text-text-muted text-2xs">—</span>}
                </div>
              </div>
            </div>

            {book.summary && (
              <div className="mt-4 pt-4 border-t border-rim">
                <p className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">Summary</p>
                <p className="text-text-secondary text-xs leading-relaxed">{book.summary}</p>
              </div>
            )}
          </div>

          {/* Ingested content */}
          {doc ? (
            <div className="bg-surface border border-rim rounded-xl p-5 max-w-3xl">
              <div className="flex items-center gap-2 mb-4">
                <FileText size={14} className="text-dawn" />
                <h3 className="text-text-primary text-sm font-medium">Ingested Content</h3>
                <span className="px-1.5 py-0.5 rounded bg-success/10 text-success border border-success/20 text-2xs font-mono">
                  {doc.type}
                </span>
              </div>

              {doc.tags && doc.tags.length > 0 && (
                <div className="flex gap-1 flex-wrap mb-3">
                  {doc.tags.map((t) => (
                    <span key={t} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-dawn/5 border border-dawn/20 text-dawn text-2xs font-mono">
                      <Tag size={8} /> {t}
                    </span>
                  ))}
                </div>
              )}

              {doc.body ? (
                <div className="bg-abyss/50 border border-rim rounded-lg p-4 max-h-[60vh] overflow-y-auto">
                  <pre className="text-text-secondary text-xs leading-relaxed whitespace-pre-wrap font-sans">
                    {doc.body.length > 50000 ? doc.body.slice(0, 50000) + "\n\n... [content truncated at 50,000 characters]" : doc.body}
                  </pre>
                </div>
              ) : (
                <div className="bg-abyss/50 border border-rim rounded-lg p-8 flex flex-col items-center gap-2">
                  <FileText size={20} className="text-text-muted/30" />
                  <p className="text-text-muted text-xs">No body content available for this document</p>
                </div>
              )}

              <div className="mt-3 flex items-center gap-2 text-2xs text-text-muted">
                <Clock size={10} />
                Source: {doc.source_ref || doc.source || "unknown"}
                <span className="mx-1">·</span>
                Updated: {formatDate(doc.updated_at)}
              </div>
            </div>
          ) : book.ingested ? (
            <div className="bg-surface border border-rim rounded-xl p-8 max-w-3xl flex flex-col items-center gap-3">
              <Layers size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">Content ingested but document node not found</p>
              <p className="text-text-muted text-xs">The book was marked as ingested but the knowledge graph node may have been deleted</p>
            </div>
          ) : (
            <div className="bg-surface border border-rim rounded-xl p-8 max-w-3xl flex flex-col items-center gap-3">
              <FileText size={24} className="text-text-muted/30" />
              <p className="text-text-muted text-sm">Not yet ingested</p>
              <p className="text-text-muted text-xs">Upload a file or use the ingest button on the library page to add content</p>
              <button onClick={() => router.push("/books")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all mt-2">
                <ArrowLeft size={12} /> Back to Library
              </button>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
