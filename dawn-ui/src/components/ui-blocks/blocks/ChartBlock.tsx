"use client";

import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import type { ChartBlock as ChartBlockT } from "@/lib/ui/schema";

const ChartRenderer = lazy(() => import("@/components/visualize/ChartRenderer"));

export default function ChartBlock({ block }: { block: ChartBlockT }) {
  if (!block.vega_spec) {
    return (
      <div className="px-3 py-2 text-2xs text-text-muted rounded-[8px] border border-rim">
        Chart data was not rendered (missing spec).
      </div>
    );
  }
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center py-6 rounded-[8px] border border-rim bg-surface/50">
          <Loader2 size={16} className="text-dawn animate-spin" />
        </div>
      }
    >
      <ChartRenderer spec={block.vega_spec} title={block.title} />
    </Suspense>
  );
}
