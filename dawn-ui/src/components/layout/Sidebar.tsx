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
  BarChart3,
  Image,
  X as XIcon,
  GitBranch,
  Route,
  FlaskConical,
  ScrollText,
  ActivitySquare,
  FolderKanban,
  Package,
  Server,
  FolderOpen,
  ListTodo,
  LayoutDashboard,
  LayoutGrid,
  ShieldCheck,
} from "lucide-react";
import clsx from "clsx";
import {
  listSessions,
  createSession,
  deleteSession,
  updateSession,
  countArtifacts,
  getPendingNodes,
  listDecisionLog,
} from "@/lib/api";
import type { ChatSession } from "@/lib/types";

// Navigation config
interface NavItem {
  href: string;
  icon: React.ElementType;
  label: string;
  badge?: number | string;
}

interface NavSectionDef {
  key: string;
  label: string;
  items: NavItem[];
}

// Primary — Dashboard and Canvas are the new top-level surfaces; Approvals
// carries a live pending-count badge. Visualize moved to Business since Canvas
// is now the primary freeform surface.
const PRIMARY_NAV: NavItem[] = [
  { href: "/", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/chat", icon: MessageSquare, label: "Chat" },
  { href: "/canvas", icon: LayoutGrid, label: "Canvas" },
  { href: "/approvals", icon: ShieldCheck, label: "Approvals" },
  { href: "/nodes", icon: Database, label: "Knowledge" },
  { href: "/memory", icon: Brain, label: "Memory" },
  { href: "/agent-tasks", icon: ListTodo, label: "Agent Tasks" },
  { href: "/agent-logs", icon: Activity, label: "Agent Logs" },
];

const TOOLS_NAV: NavItem[] = [
  { href: "/ssh", icon: Terminal, label: "SSH Hosts" },
  { href: "/osint", icon: Search, label: "OSINT" },
  { href: "/pentest", icon: Shield, label: "Pentesting" },
];

const BUSINESS_NAV: NavItem[] = [
  { href: "/projects", icon: FolderKanban, label: "Projects" },
  { href: "/files", icon: FolderOpen, label: "Files" },
  { href: "/integrations", icon: Puzzle, label: "Integrations" },
  { href: "/monitoring", icon: HeartPulse, label: "Monitoring" },
  { href: "/books", icon: BookOpen, label: "Library" },
  { href: "/artifacts", icon: Image, label: "Artifacts" },
  { href: "/visualize", icon: BarChart3, label: "Visualize" },
];

const SKILLS_NAV: NavItem[] = [
  { href: "/skills", icon: Package, label: "Skills" },
  { href: "/mcp", icon: Server, label: "MCP Servers" },
];

const DECISIONS_NAV: NavItem[] = [
  { href: "/ontology", icon: GitBranch, label: "Ontology" },
  { href: "/scenarios", icon: FlaskConical, label: "Scenarios" },
  { href: "/decisions/run", icon: Route, label: "Run Decision" },
  { href: "/decisions", icon: ScrollText, label: "Decisions" },
  { href: "/admin/data-sources", icon: ActivitySquare, label: "Data Sources" },
];

const SECTIONS: NavSectionDef[] = [
  { key: "primary", label: "Primary", items: PRIMARY_NAV },
  { key: "tools", label: "Tools", items: TOOLS_NAV },
  { key: "skills", label: "Skills", items: SKILLS_NAV },
  { key: "business", label: "Business", items: BUSINESS_NAV },
  { key: "decisions", label: "Decisions", items: DECISIONS_NAV },
];

// Default: Primary always open; others open on first visit, then remembered.
const DEFAULT_OPEN: Record<string, boolean> = {
  primary: true,
  tools: true,
  skills: true,
  business: true,
  decisions: true,
};

const STORAGE_KEY = "dawn:sidebar:sections";

function loadOpenState(): Record<string, boolean> {
  if (typeof window === "undefined") return { ...DEFAULT_OPEN };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_OPEN };
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_OPEN, ...parsed };
  } catch {
    return { ...DEFAULT_OPEN };
  }
}

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
  const [artifactCount, setArtifactCount] = useState<number>(0);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(loadOpenState);

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

  // Fetch artifact count
  const fetchArtifactCount = useCallback(async () => {
    try {
      const count = await countArtifacts();
      setArtifactCount(count);
    } catch {
      // Silently fail — not critical
    }
  }, []);

  // Fetch live pending-approvals count (pending nodes + unresolved decisions)
  const fetchPendingCount = useCallback(async () => {
    try {
      const [nodes, decisions] = await Promise.all([
        getPendingNodes().then((n) => n.length).catch(() => 0),
        listDecisionLog({ limit: 100 })
          .then((d) => d.filter((x) => !x.human_decision).length)
          .catch(() => 0),
      ]);
      setPendingCount(nodes + decisions);
    } catch {
      // Silently fail — badge just stays hidden
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    fetchArtifactCount();
    fetchPendingCount();
  }, [fetchSessions, fetchArtifactCount, fetchPendingCount]);

  // Poll for new sessions every 10s (pause when the tab is hidden)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchSessions();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchSessions]);

  // Poll artifact count every 30s (pause when the tab is hidden)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchArtifactCount();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchArtifactCount]);

  // Poll pending count every 15s (pause when the tab is hidden)
  useEffect(() => {
    const interval = setInterval(() => {
      if (!document.hidden) fetchPendingCount();
    }, 15000);
    return () => clearInterval(interval);
  }, [fetchPendingCount]);

  // Listen for custom event from ChatWindow
  useEffect(() => {
    const handler = () => fetchSessions();
    window.addEventListener("dawn:session-changed", handler);
    return () => window.removeEventListener("dawn:session-changed", handler);
  }, [fetchSessions]);

  const toggleSection = (key: string) => {
    setOpenSections((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

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

  const isActive = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

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
          "flex items-center gap-2.5 rounded-nested transition-all duration-150 group relative",
          collapsed ? "w-10 h-10 justify-center" : "h-[34px] px-[9px]",
          active ? "teal-soft text-dawn font-semibold" : "text-text-muted hover:text-text-secondary hover:bg-elevated/60",
        )}
      >
        <Icon size={16} strokeWidth={active ? 2 : 1.75} className="flex-none" />
        {!collapsed && (
          <>
            <span className="text-xs font-medium truncate">{label}</span>
            {badge ? (
              <span className="badge">{badge}</span>
            ) : (
              <span className="ml-auto" />
            )}
            {active && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
          </>
        )}
        {collapsed && active && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
        {collapsed && (
          <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-soft z-50">
            {label}
          </span>
        )}
      </Link>
    );
  };

  const NavSection = ({ def }: { def: NavSectionDef }) => {
    if (collapsed) return null;
    const open = openSections[def.key] ?? DEFAULT_OPEN[def.key];
    return (
      <div className="pt-2 px-2">
        <button
          onClick={() => toggleSection(def.key)}
          className="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-md text-text-muted hover:text-text-secondary transition-colors"
          title={open ? "Collapse section" : "Expand section"}
        >
          <ChevronDown
            size={11}
            className={clsx("flex-none transition-transform duration-200", open ? "rotate-0" : "-rotate-90")}
          />
          <span className="text-2xs font-semibold uppercase tracking-wider">{def.label}</span>
        </button>
        <div
          className={clsx(
            "overflow-hidden transition-all duration-200",
            open ? "max-h-96 opacity-100" : "max-h-0 opacity-0"
          )}
        >
          <div className="pt-0.5 space-y-[1px]">
            {def.items.map((item) => <NavLink key={item.href} {...item} />)}
          </div>
        </div>
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
        {/* Collapsible nav sections */}
        <nav className={clsx("flex flex-col pt-1 flex-shrink-0", collapsed && "items-center")}>
          {collapsed ? (
            <div className="flex flex-col items-center gap-0.5 pt-1 px-2">
              {PRIMARY_NAV.map((item) => <NavLink key={item.href} {...item} />)}
            </div>
          ) : (
            SECTIONS.map((def) => <NavSection key={def.key} def={def} />)
          )}
        </nav>

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
                      href={session.mode === "visualize" ? `/visualize?id=${session.id}` : `/chat?id=${session.id}`}
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
          className={clsx("flex items-center gap-2.5 rounded-nested transition-all duration-150 group relative", collapsed ? "w-10 h-10 justify-center" : "h-[34px] px-[9px]",
            path === "/settings" ? "teal-soft text-dawn font-semibold" : "text-text-muted hover:text-text-secondary hover:bg-elevated/60")}>
          <Settings size={16} strokeWidth={path === "/settings" ? 2 : 1.75} className="flex-none" />
          {!collapsed && <span className="text-xs font-medium">Settings</span>}
          {!collapsed && path === "/settings" && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-dawn rounded-r-full" />}
          {collapsed && (
            <span className="absolute left-12 bg-surface border border-rim text-text-primary text-2xs px-2 py-1 rounded-md whitespace-nowrap opacity-0 group-hover:opacity-100 pointer-events-none transition-opacity shadow-soft z-50">Settings</span>
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
