"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import AppShell from "@/components/layout/AppShell";
import MathTex from "@/lib/ui/Math";
import { renderMarkdown } from "@/lib/ui/markdown";
import { learnQueue, submitReview, type LearnItem } from "@/lib/api";

const RATING_LABEL: Record<number, string> = { 1: "Again", 2: "Hard", 3: "Good", 4: "Easy" };

function fmtDays(d: number): string {
  if (d <= 0.01) return "10 min";
  if (d < 1) return `${Math.round(d * 24)} h`;
  return `${Math.round(d)} d`;
}

export default function LearnReview() {
  const [items, setItems] = useState<LearnItem[]>([]);
  const [idx, setIdx] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState<{ item_id: string; rating: number; crid: string }[]>([]);
  const [reviewed, setReviewed] = useState(0);

  const load = useCallback(() => {
    learnQueue(undefined, 20)
      .then((q) => setItems(q.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const saveNow = async () => {
    // flush pending reviews (offline-tolerant: idempotency keys make retries safe)
    const batch = [...pending];
    setPending([]);
    for (const r of batch) {
      try {
        await submitReview(r.item_id, r.rating, r.crid);
      } catch { /* keep for the next flush */ setPending((p) => (p.some((x) => x.crid === r.crid) ? p : [...p, r])); }
    }
  };
  useEffect(() => { if (pending.length) void saveNow(); }, [pending]);

  const rate = async (r: number) => {
    const item = items[idx];
    const crid = `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setPending((p) => [...p, { item_id: item.id, rating: r, crid }]);
    setReviewed((n) => n + 1);
    if (idx + 1 < items.length) {
      setIdx(idx + 1);
      setRevealed(false);
    } else {
      setDone(true);
    }
  };

  const item = items[idx];
  const preview = item?._preview;

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[560px] mx-auto px-6 py-8">
          <div className="flex items-center justify-between mb-5">
            <p className="text-text-muted text-xs">{loading ? "Loading…" : `${idx + 1} / ${items.length}`}</p>
            <Link href="/learn" className="text-2xs text-text-muted hover:text-text-secondary">Exit</Link>
          </div>

          {loading ? (
            <div className="text-center text-text-muted text-sm py-16">Loading the queue…</div>
          ) : done || !item ? (
            <div className="text-center py-16 space-y-3">
              <p className="text-text-primary text-base font-medium">{items.length === 0 ? "Nothing due right now." : "Session finished."}</p>
              <p className="text-text-muted text-xs">{reviewed} reviewed</p>
              <Link href="/learn" className="inline-block px-4 py-2 rounded-lg text-xs font-medium bg-dawn/90 text-white">Back to Learn</Link>
            </div>
          ) : (
            <div className="bg-surface border border-rim rounded-2xl p-6 min-h-[280px]">
              <div className="text-sm leading-relaxed text-text-primary">{renderMarkdown(item.front)}</div>
              {revealed ? (
                <>
                  <div className="mt-4 pt-4 border-t border-rim text-sm leading-relaxed text-text-secondary">
                    {renderMarkdown(item.back)}
                  </div>
                  <div className="mt-6 grid grid-cols-4 gap-2">
                    {[1, 2, 3, 4].map((r) => (
                      <button key={r} onClick={() => rate(r)}
                        className={r === 1 ? "py-2 rounded-lg text-xs font-medium text-white bg-ember/90 hover:bg-ember" : r === 3 ? "py-2 rounded-lg text-xs font-medium text-white bg-dawn/90 hover:bg-dawn" : "py-2 rounded-lg text-xs font-medium text-text-secondary border border-rim hover:border-dawn/40"}>
                        {RATING_LABEL[r]}
                        <span className="block text-2xs opacity-70 mt-0.5">{preview?.[r] !== undefined ? fmtDays(preview[r]) : "—"}</span>
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <button onClick={() => setRevealed(true)}
                  className="mt-8 w-full py-2.5 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn">
                  Show answer
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
