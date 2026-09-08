"use client";

import AppShell from "@/components/layout/AppShell";
import AlertStrip from "@/components/dashboard/AlertStrip";
import KpiGrid from "@/components/dashboard/KpiGrid";
import ActivityFeed from "@/components/dashboard/ActivityFeed";

export default function HomePage() {
  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1180px] mx-auto px-6 sm:px-7 py-6 pb-10">
          {/* Header */}
          <div className="flex items-end justify-between mb-5">
            <div>
              <p className="eyebrow">Command center</p>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">
                Good evening. I&apos;m on watch.
              </h1>
              <p className="subtitle">
                A live view of infrastructure, knowledge, business activity, and what I&apos;m doing now.
              </p>
            </div>
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="w-[7px] h-[7px] rounded-full bg-dawn shadow-[0_0_0_4px_rgba(21,128,122,0.08)]" />
              <span className="mono">live</span>
            </div>
          </div>

          {/* Fixed vertical structure — order never changes */}
          <AlertStrip />
          <KpiGrid />
          <ActivityFeed />
        </div>
      </div>
    </AppShell>
  );
}
