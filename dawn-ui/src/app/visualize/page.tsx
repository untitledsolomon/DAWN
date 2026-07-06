"use client";

import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import VisualizeWindow from "@/components/visualize/VisualizeWindow";

function VisualizeContent() {
  return <VisualizeWindow />;
}

export default function VisualizePage() {
  return (
    <AppShell>
      <Suspense fallback={
        <div className="flex items-center justify-center h-full">
          <div className="text-text-muted text-sm">Loading visualize...</div>
        </div>
      }>
        <VisualizeContent />
      </Suspense>
    </AppShell>
  );
}
