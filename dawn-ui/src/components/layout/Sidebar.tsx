"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquare,
  Database,
  Brain,
  Settings,
  PanelLeftClose,
  PanelLeft,
  ChevronDown,
  Clock,
  Zap,
  Crown,
  User,
  Activity,
  FileText,
} from "lucide-react";
import clsx from "clsx";

// ── Navigation config ─────────────────────────────────────────────────────────────

interface NavItem {
  href: string;
  icon: React.ElementType;
  label: string;
  badge?: number | string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/chat", icon: MessageSquare, label: "Chat" },
  { href: "/nodes", icon: Database, label: "Knowledge" },
  { href: "/memory", icon: Brain, label: "Memory" },
  { href: "/agent-logs", icon: Activity, label: "Agent Logs" },
];

const SECONDARY_NAV: NavItem[] = [
  { href: "/settings", icon: Settings, label: "Settings" },
];

// ── Mock conversation history ─────────────────────────────────────────────────────

interface RecentConv {
  id: string;
  title: string;
  timestamp: Date;
}

const MOCK_RECENT: RecentConv[] = [
  { id: "1", title: "Sentinel bot status check", timestamp: new Date(Date.now() - 1000 * 60 * 30) },
  { id: "2", title: "Axis PAYE compliance", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 2) },
  { id: "3", title: "EconSim architecture review", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24) },
  { id: "4", title: "Mabruk Atelier inventory", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 36) },
  { id: "5", title: "Jarvis deployment notes", timestamp: new Date(Date.now() - 1000 * 60 * 60 * 48) },
];

// ── Component ─────────────────────────────────────────────────────────────────────

interface Props {
  collapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ collapsed, onToggle }: Props) {
  const path = usePathname();
  const [recentOpen, setRecentOpen] = useState(true);

  const timeAgo = (date: Date) => {
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    return `${Math.floor(hours / 24)}d`;
  };

  return (
    <aside
      className={clsx(
        "flex flex-col bg-surface border-r border-rim h-full transition-all duration-200 flex-shrink-0 z-30",
        collapsed ? "w-14" : "w-60",
      )}
    >
      {/* ── Workspace header ──────────────────────────────────────────────────────── */}
      <div className={clsx("flex items-center border-b border-rim flex-shrink-0", collapsed ? "justify-center px-2 py-3" : "px-3 py-2.5")}>
        {collapsed ? (
          <div className="w-8 h-8 rounded-lg bg-dawn/10 border border-dawn/25 flex items-center justify-center">
            <Zap size={14} className="text-dawn" />
          </div>
        ) : (
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-dawn/10 border border-dawn/25 flex items-center justify-center">
                <Zap size={14} className="text-dawn" />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-text-primary text-sm font-semibold tracking-tight">DAWN</span>
                  <span className="inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-ember/10 text-ember text-[9px] font-mono font-medium uppercase tracking-wider">
                    <Crown size={8} strokeWidth={2.5} />
                    Owner
                  </span>
                </div>
                <p className="text-text-muted text-2xs leading-none mt-0.5">Regent Knowledge Layer</p>
              </div>
            </div>
            <button
              onClick={onToggle}
              className="w-6 h-6 flex items-center justify-center rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
              title="Collapse sidebar"
            >
              <PanelLeftClose size={13} />
            </button>
          </div>
        )}
      </div>

      {/* ── Primary navigation ────────────────────────────────────────────────────── */}
      <nav className={clsx("flex flex-col gap-0.5 pt-2 px-2", collapsed && "items-center")}>
        {PRIMARY_NAV.map(({ href, icon: Icon, label, badge }) => {
          const active = path.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={clsx(
                "flex items-center gap-2.5 rounded-lg transition-all duration-150 group relative",
                collapsed
                  ? "w-10 h-10 justify-center"
                  : "px-2.5 py-2",
                active
                  ? "bg-dawn/10 text-dawn"
                  : "text-text-muted hover:text-text-secondary hover:bg-elevated/60",
              )}
            >
              <Icon size={16} strokeWidth={active ? 2 : 1.75} />
              {!collapsed && (
                <>
                  <span className="text-xs font-medium">{label}</span>
                  {badge && (
                    <span className="ml-auto text-2xs font-mono px-1.5 py-0.5 rounded-full bg-ember/15 text-ember">
                      {badge}
                    </span>
                  )}
                  {active && (
                    <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />
                  )}
                </>
              )}
              {collapsed && active && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />
              )}
              {/* Tooltip for collapsed state */}
              {collapsed && (
                <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-card z-50">
                  {label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* ── Recent conversations ──────────────────────────────────────────────────── */}
      {!collapsed && (
        <div className="flex-1 flex flex-col min-h-0 pt-3 px-2">
          <button
            onClick={() => setRecentOpen(!recentOpen)}
            className="flex items-center gap-1.5 px-2 py-1.5 rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/40 transition-all text-2xs font-medium uppercase tracking-wider"
          >
            <ChevronDown
              size={10}
              className={clsx("transition-transform", recentOpen && "rotate-0", !recentOpen && "-rotate-90")}
            />
            <Clock size={10} />
            Recent
          </button>

          {recentOpen && (
            <div className="flex-1 overflow-y-auto sidebar-scroll mt-1 space-y-0.5">
              {MOCK_RECENT.map((conv) => (
                <button
                  key={conv.id}
                  className="w-full text-left px-2.5 py-1.5 rounded-lg hover:bg-elevated/50 transition-colors group"
                >
                  <div className="flex items-start justify-between gap-1">
                    <span className="text-text-secondary text-xs truncate flex-1 group-hover:text-text-primary transition-colors">
                      {conv.title}
                    </span>
                    <span className="text-text-muted text-2xs font-mono flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                      {timeAgo(conv.timestamp)}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Bottom section ────────────────────────────────────────────────────────── */}
      <div className={clsx("border-t border-rim pt-1 pb-2 px-2 flex flex-col gap-0.5", collapsed && "items-center")}>
        {/* Settings — now links to /settings page */}
        <Link
          href="/settings"
          title={collapsed ? "Settings" : undefined}
          className={clsx(
            "flex items-center gap-2.5 rounded-lg transition-all duration-150 group relative",
            collapsed ? "w-10 h-10 justify-center" : "px-2.5 py-2",
            path === "/settings"
              ? "bg-dawn/10 text-dawn"
              : "text-text-muted hover:text-text-secondary hover:bg-elevated/60",
          )}
        >
          <Settings size={16} strokeWidth={path === "/settings" ? 2 : 1.75} />
          {!collapsed && <span className="text-xs font-medium">Settings</span>}
          {!collapsed && path === "/settings" && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />
          )}
          {collapsed && (
            <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-card z-50">
              Settings
            </span>
          )}
        </Link>

        {/* User badge */}
        {!collapsed && (
          <div className="flex items-center gap-2 px-2.5 py-2 mt-0.5">
            <div className="w-6 h-6 rounded-md bg-dawn/10 border border-dawn/20 flex items-center justify-center">
              <User size={11} className="text-dawn" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-text-primary text-xs font-medium truncate">Solomon John</p>
              <p className="text-text-muted text-2xs truncate">Paperclip VPS</p>
            </div>
            <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse-dot" />
          </div>
        )}
      </div>
    </aside>
  );
}
