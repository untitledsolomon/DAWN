"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
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
  Plus,
  Trash2,
  Edit3,
  Check,
  X,
  Terminal,
  Search,
  Shield,
  Puzzle,
  HeartPulse,
  BookOpen,
  ListTodo,
  X as XIcon,
} from "lucide-react";
import clsx from "clsx";
import { listSessions, createSession, deleteSession, updateSession } from "@/lib/api";
import type { ChatSession } from "@/lib/types";

// Navigation config
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

const TOOLS_NAV: NavItem[] = [
  { href: "/ssh", icon: Terminal, label: "SSH Hosts" },
  { href: "/osint", icon: Search, label: "OSINT" },
  { href: "/pentest", icon: Shield, label: "Pentesting" },
];

const BUSINESS_NAV: NavItem[] = [
  { href: "/integrations", icon: Puzzle, label: "Integrations" },
  { href: "/monitoring", icon: HeartPulse, label: "Monitoring" },
  { href: "/books", icon: BookOpen, label: "Library" },
];

// Component
interface Props {
  collapsed: boolean;
  onToggle: () => void;
  onMobileClose?: () => void;
}

export default function Sidebar({ collapsed, onToggle, onMobileClose }: Props) {
  const path = usePathname();
  const router = useRouter();
  const [recentOpen, setRecentOpen] = useState(true);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  // Fetch sessions
  const fetchSessions = useCallback(async () => {
    try {
      const data = await listSessions();
      setSessions(data);
    } catch (err) {
      console.error("[Sidebar] Failed to load sessions:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Poll for new sessions every 10s
  useEffect(() => {
    const interval = setInterval(fetchSessions, 10000);
    return () => clearInterval(interval);
  }, [fetchSessions]);

  // Listen for custom event from ChatWindow
  useEffect(() => {
    const handler = () => fetchSessions();
    window.addEventListener("dawn:session-changed", handler);
    return () => window.removeEventListener("dawn:session-changed", handler);
  }, [fetchSessions]);

  const handleNewChat = async () => {
    try {
      const session = await createSession();
      router.push(`/chat?id=${session.id}`);
      setSessions((prev) => [{ ...session, message_count: 0 }, ...prev]);
      onMobileClose?.();
    } catch (err) {
      console.error("[Sidebar] Failed to create session:", err);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      const params = new URLSearchParams(window.location.search);
      if (params.get("id") === id) {
        router.push("/chat");
      }
    } catch (err) {
      console.error("[Sidebar] Failed to delete session:", err);
    }
  };

  const handleRenameStart = (e: React.MouseEvent, id: string, currentTitle: string) => {
    e.stopPropagation();
    setEditingId(id);
    setEditTitle(currentTitle);
  };

  const handleRenameConfirm = async (e: React.MouseEvent | React.KeyboardEvent, id: string) => {
    e.stopPropagation();
    const title = editTitle.trim() || "New Chat";
    try {
      await updateSession(id, title);
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    } catch (err) {
      console.error("[Sidebar] Failed to rename session:", err);
    }
    setEditingId(null);
    setEditTitle("");
  };

  const handleRenameCancel = (e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(null);
    setEditTitle("");
  };

  const timeAgo = (dateStr: string) => {
    const date = new Date(dateStr);
    const mins = Math.floor((Date.now() - date.getTime()) / 1000 / 60);
    if (mins < 1) return "now";
    if (mins < 60) return `${mins}m`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d`;
    return `${Math.floor(days / 30)}mo`;
  };

  const currentSessionId = typeof window !== "undefined"
    ? new URLSearchParams(window.location.search).get("id")
    : null;

  const isActive = (href: string) => path.startsWith(href);

  const handleNavClick = () => {
    onMobileClose?.();
  };

  const NavLink = ({ href, icon: Icon, label, badge }: NavItem) => {
    const active = isActive(href);
    return (
      <Link
        href={href}
        onClick={handleNavClick}
        title={collapsed ? label : undefined}
        className={clsx(
          "flex items-center gap-2.5 rounded-lg transition-all duration-150 group relative",
          collapsed ? "w-10 h-10 justify-center" : "px-2.5 py-2",
          active ? "bg-dawn/10 text-dawn" : "text-text-muted hover:text-text-secondary hover:bg-elevated/60",
        )}
      >
        <Icon size={16} strokeWidth={active ? 2 : 1.75} />
        {!collapsed && (
          <>
            <span className="text-xs font-medium">{label}</span>
            {badge && (
              <span className="ml-auto text-2xs font-mono px-1.5 py-0.5 rounded-full bg-ember/15 text-ember">{badge}</span>
            )}
            {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
          </>
        )}
        {collapsed && active && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
        {collapsed && (
          <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-card z-50">
            {label}
          </span>
        )}
      </Link>
    );
  };

  const NavSection = ({ label, items }: { label: string; items: NavItem[] }) => {
    if (collapsed) return null;
    return (
      <div className="pt-3 px-2">
        <p className="text-text-muted text-2xs font-medium uppercase tracking-wider px-2.5 pb-1">{label}</p>
        {items.map((item) => <NavLink key={item.href} {...item} />)}
      </div>
    );
  };

  return (
    <aside
      className={clsx(
        "flex flex-col bg-surface border-r border-rim h-full transition-all duration-200 flex-shrink-0 z-30",
        collapsed ? "w-14" : "w-60",
      )}
    >
      {/* Workspace header */}
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
                    <Crown size={8} strokeWidth={2.5} /> Owner
                  </span>
                </div>
                <p className="text-text-muted text-2xs leading-none mt-0.5">Regent Knowledge Layer</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {/* Mobile close button */}
              <button
                onClick={onMobileClose}
                className="md:hidden w-6 h-6 flex items-center justify-center rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
                title="Close sidebar"
              >
                <XIcon size={13} />
              </button>
              <button
                onClick={onToggle}
                className="hidden md:flex w-6 h-6 items-center justify-center rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all"
                title="Collapse sidebar"
              >
                <PanelLeftClose size={13} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Scrollable nav + recent area */}
      <div className="flex-1 min-h-0 overflow-y-auto sidebar-scroll flex flex-col">
        {/* Primary navigation */}
        <nav className={clsx("flex flex-col gap-0.5 pt-2 px-2 flex-shrink-0", collapsed && "items-center")}>
          {PRIMARY_NAV.map((item) => <NavLink key={item.href} {...item} />)}
        </nav>

        {/* Tools section */}
        <div className="flex-shrink-0"><NavSection label="Tools" items={TOOLS_NAV} /></div>

        {/* Business section */}
        <div className="flex-shrink-0"><NavSection label="Business" items={BUSINESS_NAV} /></div>

        {/* Recent conversations */}
        {!collapsed && (
          <div className="flex flex-col pt-3 px-2">
          <div className="flex items-center justify-between px-2 py-1.5">
            <button onClick={() => setRecentOpen(!recentOpen)} className="flex items-center gap-1.5 rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/40 transition-all text-2xs font-medium uppercase tracking-wider">
              <ChevronDown size={10} className={clsx("transition-transform", recentOpen && "rotate-0", !recentOpen && "-rotate-90")} />
              <Clock size={10} /> Recent
            </button>
            <button onClick={handleNewChat} className="w-5 h-5 flex items-center justify-center rounded-md text-text-muted hover:text-text-secondary hover:bg-elevated/60 transition-all" title="New chat">
              <Plus size={12} />
            </button>
          </div>

          {recentOpen && (
            <div className="mt-1 space-y-0.5">
              {loading ? (
                <div className="px-2.5 py-3 text-center text-text-muted text-2xs">Loading...</div>
              ) : sessions.length === 0 ? (
                <div className="px-2.5 py-3 text-center text-text-muted text-2xs">No conversations yet</div>
              ) : (
                sessions.map((session) => (
                  <div key={session.id} className="group relative">
                    <Link
                      href={`/chat?id=${session.id}`}
                      onClick={handleNavClick}
                      className={clsx(
                        "w-full text-left px-2.5 py-1.5 rounded-lg transition-colors flex items-start justify-between gap-1",
                        currentSessionId === session.id ? "bg-dawn/10 text-dawn" : "hover:bg-elevated/50 text-text-secondary hover:text-text-primary",
                      )}
                    >
                      {editingId === session.id ? (
                        <div className="flex items-center gap-1 flex-1 min-w-0" onClick={(e) => e.preventDefault()}>
                          <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter") handleRenameConfirm(e, session.id); if (e.key === "Escape") handleRenameCancel(e as unknown as React.MouseEvent); }}
                            className="flex-1 bg-elevated border border-rim rounded px-1.5 py-0.5 text-xs text-text-primary outline-none" autoFocus onClick={(e) => e.stopPropagation()} />
                          <button onClick={(e) => handleRenameConfirm(e, session.id)} className="w-4 h-4 flex items-center justify-center text-success hover:text-success/80"><Check size={10} /></button>
                          <button onClick={handleRenameCancel} className="w-4 h-4 flex items-center justify-center text-text-muted hover:text-text-secondary"><X size={10} /></button>
                        </div>
                      ) : (
                        <>
                          <span className="text-xs truncate flex-1">{session.title}</span>
                          <span className="text-2xs font-mono flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-text-muted">{timeAgo(session.updated_at)}</span>
                        </>
                      )}
                    </Link>
                    {editingId !== session.id && (
                      <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button onClick={(e) => handleRenameStart(e, session.id, session.title)} className="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-text-secondary hover:bg-elevated/60" title="Rename"><Edit3 size={10} /></button>
                        <button onClick={(e) => handleDelete(e, session.id)} className="w-5 h-5 flex items-center justify-center rounded text-text-muted hover:text-ember hover:bg-ember/10" title="Delete"><Trash2 size={10} /></button>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
      </div>
      {/* end scrollable nav + recent area */}

      {/* Bottom section */}
      <div className={clsx("border-t border-rim pt-1 pb-2 px-2 flex flex-col gap-0.5 flex-shrink-0", collapsed && "items-center")}>
        <Link href="/settings" onClick={handleNavClick} title={collapsed ? "Settings" : undefined}
          className={clsx("flex items-center gap-2.5 rounded-lg transition-all duration-150 group relative", collapsed ? "w-10 h-10 justify-center" : "px-2.5 py-2",
            path === "/settings" ? "bg-dawn/10 text-dawn" : "text-text-muted hover:text-text-secondary hover:bg-elevated/60")}>
          <Settings size={16} strokeWidth={path === "/settings" ? 2 : 1.75} />
          {!collapsed && <span className="text-xs font-medium">Settings</span>}
          {!collapsed && path === "/settings" && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
          {collapsed && (
            <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-card z-50">Settings</span>
          )}
        </Link>

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
