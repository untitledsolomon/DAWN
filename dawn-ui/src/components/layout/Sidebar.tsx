"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquare, Database, Brain, Settings, Zap } from "lucide-react";
import clsx from "clsx";

const NAV = [
  { href: "/chat",   icon: MessageSquare, label: "Chat" },
  { href: "/nodes",  icon: Database,      label: "Knowledge" },
  { href: "/memory", icon: Brain,         label: "Memory" },
];

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside className="fixed left-0 top-0 h-full w-14 bg-surface border-r border-rim flex flex-col items-center py-4 gap-1 z-40">
      {/* Logo */}
      <div className="w-8 h-8 rounded-lg bg-dawn/10 border border-dawn/30 flex items-center justify-center mb-4">
        <Zap size={14} className="text-dawn" />
      </div>

      {/* Nav items */}
      <nav className="flex flex-col items-center gap-1 flex-1">
        {NAV.map(({ href, icon: Icon, label }) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={label}
              className={clsx(
                "w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-150 group relative",
                active
                  ? "bg-dawn/15 text-dawn"
                  : "text-text-muted hover:text-text-secondary hover:bg-elevated",
              )}
            >
              <Icon size={16} strokeWidth={1.75} />
              {/* Tooltip */}
              <span className="absolute left-12 bg-surface border border-rim text-text-primary text-xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity">
                {label}
              </span>
              {/* Active indicator */}
              {active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Settings at bottom */}
      <Link
        href="/settings"
        title="Settings"
        className="w-9 h-9 rounded-lg flex items-center justify-center text-text-muted hover:text-text-secondary hover:bg-elevated transition-all"
      >
        <Settings size={16} strokeWidth={1.75} />
      </Link>
    </aside>
  );
}
