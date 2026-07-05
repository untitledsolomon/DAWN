"use client";

import { usePathname } from "next/navigation";
import { PanelLeft, Menu, Zap, Settings, X } from "lucide-react";

interface Props {
  onToggleSidebar: () => void;
  onToggleMobileSidebar: () => void;
  mobileSidebarOpen: boolean;
}

const PAGE_TITLES: Record<string, { title: string; subtitle: string }> = {
  "/chat": { title: "Chat", subtitle: "Ask DAWN anything" },
  "/nodes": { title: "Knowledge Base", subtitle: "Browse and manage the knowledge graph" },
  "/memory": { title: "Memory & Ingestion", subtitle: "Review facts, upload files, ingest data" },
  "/agent-logs": { title: "Agent Logs", subtitle: "Recent agent task executions and tool calls" },
  "/settings": { title: "Settings", subtitle: "Configure DAWN to your preferences" },
};

export default function TopBar({ onToggleSidebar, onToggleMobileSidebar, mobileSidebarOpen }: Props) {
  const path = usePathname();
  const page = PAGE_TITLES[path] || { title: "DAWN", subtitle: "Digital AI Working Network" };

  return (
    <header className="flex-shrink-0 bg-surface border-b border-rim relative z-50">
      <div className="dawn-line" />
      <div className="flex items-center justify-between px-3 sm:px-4 py-2">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          {/* Mobile hamburger */}
          <button
            onClick={onToggleMobileSidebar}
            className="md:hidden w-8 h-8 flex items-center justify-center rounded-lg text-text-primary hover:text-dawn hover:bg-dawn/10 transition-all active:scale-95 flex-shrink-0"
            title={mobileSidebarOpen ? "Close sidebar" : "Open sidebar"}
            aria-label={mobileSidebarOpen ? "Close sidebar" : "Open sidebar"}
          >
            {mobileSidebarOpen ? <X size={15} /> : <Menu size={15} />}
          </button>

          {/* Desktop collapse button */}
          <button
            onClick={onToggleSidebar}
            className="hidden md:flex w-7 h-7 items-center justify-center rounded-lg text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all flex-shrink-0"
            title="Toggle sidebar"
          >
            <PanelLeft size={14} />
          </button>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-text-primary text-sm font-medium truncate">{page.title}</span>
              <span className="text-text-muted text-2xs font-mono bg-elevated/50 border border-rim px-1.5 py-0.5 rounded hidden sm:inline">
                v3.0
              </span>
            </div>
            <p className="text-text-muted text-2xs leading-none mt-0.5 truncate hidden sm:block">{page.subtitle}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3 flex-shrink-0">
          {/* Status indicator — hidden on smallest screens */}
          <div className="hidden xs:flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-dot" />
            <span className="text-text-muted text-2xs font-mono uppercase tracking-wider hidden sm:inline">Online</span>
          </div>

          {/* Instance badge */}
          <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-elevated/50 border border-rim">
            <Zap size={10} className="text-dawn" />
            <span className="text-text-muted text-2xs font-mono hidden sm:inline">Paperclip VPS</span>
          </div>
        </div>
      </div>
    </header>
  );
}
