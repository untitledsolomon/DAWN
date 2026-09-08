"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Send, Loader2 } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import ArtifactCard from "@/components/canvas/ArtifactCard";
import { listArtifacts, createSession } from "@/lib/api";
import type { Artifact } from "@/lib/types";

const PAGE_SIZE = 10;

export default function CanvasPage() {
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const offsetRef = useRef(0);

  const loadPage = useCallback(async (offset: number, append: boolean) => {
    try {
      const data = await listArtifacts({ limit: PAGE_SIZE, offset });
      setArtifacts((prev) => (append ? [...prev, ...data] : data));
      setHasMore(data.length === PAGE_SIZE);
      offsetRef.current = offset + data.length;
    } catch (err) {
      console.error("[Canvas] Failed to load artifacts:", err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    loadPage(0, false);
  }, [loadPage]);

  const loadMore = () => {
    setLoadingMore(true);
    loadPage(offsetRef.current, true);
  };

  const handleRun = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    try {
      // There's no clean standalone "ask DAWN that renders to Canvas"
      // endpoint, so we create a chat session (mode "visualize" so the agent
      // loop can produce artifacts) and route the user there — the new
      // artifact will land back on Canvas via the artifacts feed.
      const session = await createSession(`Canvas - ${text.slice(0, 40)}`, "visualize");
      window.location.href = `/visualize?id=${session.id}`;
    } catch (err) {
      console.error("[Canvas] Failed to create session:", err);
    } finally {
      setSending(false);
    }
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-[1180px] mx-auto px-6 sm:px-7 py-6 pb-32">
            {/* Header */}
            <div className="mb-6">
              <p className="eyebrow">Workspace</p>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">Canvas</h1>
              <p className="subtitle">
                A looser surface for artifacts, explanations, and follow-up investigation.
              </p>
            </div>

            {/* Artifact feed — single column, generous vertical whitespace */}
            <div className="flex flex-col gap-7">
              {loading ? (
                <div className="flex items-center justify-center py-16">
                  <Loader2 size={20} className="text-dawn animate-spin" />
                </div>
              ) : artifacts.length === 0 ? (
                <div className="py-16 text-center text-text-muted text-sm">
                  No artifacts yet. Ask DAWN to investigate or drill down below.
                </div>
              ) : (
                artifacts.map((artifact) => (
                  <ArtifactCard key={artifact.id} artifact={artifact} />
                ))
              )}

              {hasMore && artifacts.length > 0 && (
                <div className="flex justify-center">
                  <button
                    onClick={loadMore}
                    disabled={loadingMore}
                    className="btn outline-teal"
                  >
                    {loadingMore ? "Loading…" : "Load more"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Persistent input bar — fixed at the bottom of the page */}
        <div className="flex-shrink-0 px-6 sm:px-7 pb-6">
          <div className="max-w-[1180px] mx-auto">
            <div className="inputbar">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleRun(); }}
                placeholder="Ask DAWN to investigate or drill down on this canvas…"
                className="flex-1 bg-transparent outline-none px-2.5 py-2 text-text-primary text-sm placeholder:text-text-muted"
              />
              <button onClick={handleRun} disabled={!input.trim() || sending} className="btn primary">
                {sending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
                Run
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
