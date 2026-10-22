"use client";

import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import type { EmbedBlock as EmbedBlockT } from "@/lib/ui/schema";

const ExplainerRenderer = lazy(() => import("@/components/visualize/ExplainerRenderer"));

// Tier 2 block: a sandboxed HTML explainer (the explainer pipeline, hardened in
// Phase 0 — allow-scripts only, verified postMessage source).
export default function EmbedBlock({ block }: { block: EmbedBlockT }) {
  if (!block.code) {
    return <div className="text-2xs text-text-muted">Embedded content empty.</div>;
  }
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-8 rounded-[8px] border border-rim bg-surface/50">
          <Loader2 size={16} className="text-dawn animate-spin" />
        </div>
      }
    >
      <ExplainerRenderer code={block.code} title={block.title} />
    </Suspense>
  );
}
