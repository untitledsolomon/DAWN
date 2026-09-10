"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { Loader2, LayoutGrid, MessageSquare } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import ArtifactCard from "@/components/canvas/ArtifactCard";
import VisualizeWindow from "@/components/visualize/VisualizeWindow";
import { listArtifacts } from "@/lib/api";
import type { Artifact } from "@/lib/types";
import clsx from "clsx";

const PAGE_SIZE = 10;

type View = "chat" | "artifacts";

/**
 * Unified Canvas — merges the live streaming chat session (formerly the
 * /visualize page's VisualizeWindow) with the artifact-feed browsing view that
 * used to be Canvas's only surface. Both jobs — "actively work on something
 * new" and "browse everything I've made" — now live on one page.
 */
export default function CanvasPage() {
  const [view, setView] = useState<View>("chat");
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
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

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* View switcher */}
        <div className="flex-shrink-0 px-6 sm:px-7 pt-5">
          <div className="max-w-[1180px] mx-auto flex items-center justify-between">
            <div>
              <p className="eyebrow">Workspace</p>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">Canvas</h1>
              <p className="subtitle">
                Ask DAWN, or browse everything you&apos;ve made.
              </p>
            </div>
            <div className="inline-flex items-center gap-0.5 p-0.5 rounded-lg bg-elevated/60 border border-rim">
              <button
                onClick={() => setView("chat")}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                  view === "chat" ? "bg-dawn/90 text-white shadow-soft" : "text-text-muted hover:text-text-secondary"
                )}
              >
                <MessageSquare size={12} />
                Chat
              </button>
              <button
                onClick={() => setView("artifacts")}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-all",
                  view === "artifacts" ? "bg-dawn/90 text-white shadow-soft" : "text-text-muted hover:text-text-secondary"
                )}
              >
                <LayoutGrid size={12} />
                Artifacts
              </button>
            </div>
          </div>
        </div>

        <div className="flex-1 min-h-0">
          {view === "chat" ? (
            <Suspense fallback={
              <div className="flex items-center justify-center h-full">
                <div className="text-text-muted text-sm">Loading conversation...</div>
              </div>
            }>
              <VisualizeWindow />
            </Suspense>
          ) : (
            <div className="h-full overflow-y-auto">
              <div className="max-w-[1180px] mx-auto px-6 sm:px-7 py-6 pb-10">
                {/* Artifact feed — single column, generous vertical whitespace */}
                <div className="flex flex-col gap-7">
                  {loading ? (
                    <div className="flex items-center justify-center py-16">
                      <Loader2 size={20} className="text-dawn animate-spin" />
                    </div>
                  ) : artifacts.length === 0 ? (
                    <div className="py-16 text-center text-text-muted text-sm">
                      No artifacts yet. Ask DAWN to investigate or drill down in the Chat tab.
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
          )}
        </div>
      </div>
    </AppShell>
  );
}
