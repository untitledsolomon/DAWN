"use client";

import { useState, useEffect, useCallback } from "react";
import {
  BookOpen,
  Plus,
  Trash2,
  RefreshCw,
  ChevronDown,
  BookMarked,
  GraduationCap,
  Lightbulb,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";

interface Book {
  id: string;
  title: string;
  author: string | null;
  category: string | null;
  tags: string[];
  ingested: boolean;
  ingestion_status: string;
  summary: string | null;
  created_at: string;
}

interface KnowledgeGap {
  id: string;
  topic: string;
  context: string | null;
  frequency: number;
  is_addressed: boolean;
}

const BASE = process.env.NEXT_PUBLIC_DAWN_API_URL || "http://localhost:8000";
const KEY = process.env.NEXT_PUBLIC_DAWN_API_KEY || "";

const headers = () => ({
  "Content-Type": "application/json",
  "x-api-key": KEY,
});

const CATEGORIES = [
  "computer_science", "security", "business", "engineering", "mathematics",
  "artificial_intelligence", "networking", "economics", "design",
];

export default function BooksPage() {
  const [books, setBooks] = useState<Book[]>([]);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [filter, setFilter] = useState<string | null>(null);
  const [form, setForm] = useState({ title: "", author: "", category: "computer_science", tags: "", notes: "" });

  const load = useCallback(async () => {
    try {
      const qs = filter ? `?category=${filter}` : "";
      const [bRes, gRes] = await Promise.all([
        fetch(`${BASE}/books${qs}`, { headers: headers() }),
        fetch(`${BASE}/knowledge-gaps`, { headers: headers() }),
      ]);
      if (bRes.ok) setBooks(await bRes.json());
      if (gRes.ok) setGaps(await gRes.json());
    } catch (e) {
      console.error("Failed to load books:", e);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    try {
      const res = await fetch(`${BASE}/books`, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          ...form,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        }),
      });
      if (res.ok) {
        setShowForm(false);
        setForm({ title: "", author: "", category: "computer_science", tags: "", notes: "" });
        load();
      }
    } catch (e) {
      console.error("Failed to add book:", e);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this book?")) return;
    try {
      await fetch(`${BASE}/books/${id}`, { method: "DELETE", headers: headers() });
      setBooks((prev) => prev.filter((b) => b.id !== id));
    } catch (e) {
      console.error("Failed to delete book:", e);
    }
  };

  const handleIngest = async (id: string) => {
    try {
      await fetch(`${BASE}/books/${id}/ingest`, { method: "POST", headers: headers() });
      load();
    } catch (e) {
      console.error("Failed to ingest book:", e);
    }
  };

  const handleAddressGap = async (id: string) => {
    try {
      await fetch(`${BASE}/knowledge-gaps/${id}/address`, { method: "POST", headers: headers() });
      setGaps((prev) => prev.map((g) => g.id === id ? { ...g, is_addressed: true } : g));
    } catch (e) {
      console.error("Failed to address gap:", e);
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Library</h1>
            <p className="text-text-muted text-2xs">Books, learning, and knowledge gaps</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowForm(!showForm)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all">
              <Plus size={12} /> Add Book
            </button>
            <button onClick={load} className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all">
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
          </div>
        </header>

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
                        <div className="flex items-start gap-3">
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
                            <button onClick={() => handleIngest(book.id)}
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
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-2xs font-mono ${
                          book.ingestion_status === "complete" ? "bg-success/10 text-success border border-success/20" :
                          book.ingestion_status === "ingesting" ? "bg-dawn/10 text-dawn border border-dawn/20" :
                          "bg-elevated/50 text-text-muted border border-rim"
                        }`}>
                          {book.ingestion_status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Knowledge gaps */}
              {gaps.filter((g) => !g.is_addressed).length > 0 && (
                <div>
                  <h3 className="text-text-secondary text-xs font-medium uppercase tracking-wider mb-3 flex items-center gap-2">
                    <Lightbulb size={12} /> Knowledge Gaps
                  </h3>
                  <div className="space-y-2 max-w-4xl">
                    {gaps.filter((g) => !g.is_addressed).map((gap) => (
                      <div key={gap.id} className="bg-surface border border-rim rounded-xl px-4 py-3 flex items-center justify-between">
                        <div>
                          <p className="text-text-primary text-sm font-medium">{gap.topic}</p>
                          {gap.context && <p className="text-text-muted text-xs">{gap.context}</p>}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-text-muted text-2xs font-mono">Seen {gap.frequency}x</span>
                          <button onClick={() => handleAddressGap(gap.id)}
                            className="px-2 py-1 rounded text-2xs font-medium text-dawn hover:bg-dawn/10 transition-all">
                            Address
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {books.length === 0 && gaps.length === 0 && (
                <div className="flex flex-col items-center justify-center h-48 gap-3">
                  <BookMarked size={24} className="text-text-muted/30" />
                  <p className="text-text-muted text-sm">No books in the library</p>
                  <p className="text-text-muted text-xs">Add books to start building DAWN's knowledge</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
