"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Database,
  Brain,
  MessageSquare,
  Image,
  ArrowRight,
  Search,
  GitBranch,
  BookOpen,
  Zap,
} from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import {
  countNodes,
  countMemories,
  countArtifacts,
  listSessions,
} from "@/lib/api";

interface Stats {
  nodes: number;
  memories: number;
  artifacts: number;
  sessions: number;
}

const QUICK_LINKS = [
  {
    href: "/chat",
    icon: MessageSquare,
    label: "Chat",
    desc: "Ask DAWN anything",
  },
  {
    href: "/nodes",
    icon: Database,
    label: "Knowledge",
    desc: "Browse the knowledge graph",
  },
  {
    href: "/memory",
    icon: Brain,
    label: "Memory",
    desc: "Facts, memories & ingestion",
  },
  {
    href: "/artifacts",
    icon: Image,
    label: "Artifacts",
    desc: "Charts, tables & files",
  },
  {
    href: "/visualize",
    icon: GitBranch,
    label: "Visualize",
    desc: "Data visualization",
  },
  {
    href: "/books",
    icon: BookOpen,
    label: "Library",
    desc: "Books & documents",
  },
];

export default function HomePage() {
  const router = useRouter();
  const [stats, setStats] = useState<Stats>({
    nodes: 0,
    memories: 0,
    artifacts: 0,
    sessions: 0,
  });
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");

  const loadStats = useCallback(async () => {
    try {
      const [nodes, memories, artifacts, sessions] = await Promise.all([
        countNodes().catch(() => 0),
        countMemories("active").catch(() => 0),
        countArtifacts().catch(() => 0),
        listSessions().then((s) => s.length).catch(() => 0),
      ]);
      setStats({ nodes, memories, artifacts, sessions });
    } catch {
      // keep zeros on failure
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      router.push(`/chat?q=${encodeURIComponent(query.trim())}`);
    }
  };

  const statCards = [
    { label: "Knowledge nodes", value: stats.nodes, icon: Database },
    { label: "Memories", value: stats.memories, icon: Brain },
    { label: "Artifacts", value: stats.artifacts, icon: Image },
    { label: "Sessions", value: stats.sessions, icon: MessageSquare },
  ];

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10 sm:py-16">
          {/* Hero */}
          <div className="text-center mb-10 sm:mb-14">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-rim bg-surface text-text-muted text-2xs font-mono uppercase tracking-wider mb-6">
              <Zap size={10} className="text-dawn" />
              Digital AI Working Network
            </div>
            <h1 className="text-text-primary text-3xl sm:text-4xl font-semibold tracking-tight">
              Good morning.
            </h1>
            <p className="text-text-secondary text-sm sm:text-base mt-3 max-w-md mx-auto">
              Your knowledge layer is ready. Ask, explore, or pick up where you
              left off.
            </p>

            {/* Search */}
            <form
              onSubmit={submitSearch}
              className="mt-8 max-w-lg mx-auto flex items-center gap-2 bg-surface border border-rim rounded-xl px-4 py-3 focus-within:border-dawn/40 focus-within:shadow-soft transition-all"
            >
              <Search size={16} className="text-text-muted flex-shrink-0" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask DAWN something…"
                className="flex-1 bg-transparent text-text-primary text-sm placeholder:text-text-muted outline-none"
              />
              <button
                type="submit"
                className="flex items-center gap-1 text-text-muted hover:text-dawn text-2xs font-medium transition-colors"
              >
                <span className="hidden sm:inline">Ask</span>
                <ArrowRight size={14} />
              </button>
            </form>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-10 sm:mb-14">
            {statCards.map(({ label, value, icon: Icon }) => (
              <div
                key={label}
                className="bg-surface border border-rim rounded-xl p-4 flex flex-col gap-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-text-muted text-2xs font-medium uppercase tracking-wider">
                    {label}
                  </span>
                  <Icon size={14} className="text-dawn" />
                </div>
                <span className="text-text-primary text-2xl font-semibold tracking-tight">
                  {loading ? "–" : value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>

          {/* Quick links */}
          <div className="mb-10">
            <h2 className="text-text-secondary text-2xs font-semibold uppercase tracking-wider mb-3 px-1">
              Quick links
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {QUICK_LINKS.map(({ href, icon: Icon, label, desc }) => (
                <Link
                  key={href}
                  href={href}
                  className="group flex items-center gap-3 bg-surface border border-rim rounded-xl p-4 hover:border-dawn/30 hover:shadow-soft transition-all"
                >
                  <div className="w-9 h-9 rounded-lg bg-elevated/60 border border-rim flex items-center justify-center flex-shrink-0 group-hover:border-dawn/30">
                    <Icon size={16} className="text-text-secondary group-hover:text-dawn transition-colors" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-text-primary text-sm font-medium">{label}</p>
                    <p className="text-text-muted text-2xs truncate">{desc}</p>
                  </div>
                  <ArrowRight size={14} className="text-text-muted group-hover:text-dawn group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                </Link>
              ))}
            </div>
          </div>

          {/* Recent / status footer */}
          <div className="flex items-center justify-center gap-2 text-text-muted text-2xs font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-dot" />
            <span>DAWN online</span>
            <span>·</span>
            <span>Regent Knowledge Layer</span>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
