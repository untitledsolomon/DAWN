"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { GraduationCap, Plus, Play } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { listLearnTopics, createLearnTopic, learnStats, type LearnTopic } from "@/lib/api";

interface Stats { totals?: { new: number; learning: number; mastered: number; due: number }; due?: number }

export default function LearnHome() {
  const [topics, setTopics] = useState<LearnTopic[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [title, setTitle] = useState("");
  const [goal, setGoal] = useState("");

  const load = () => {
    listLearnTopics().then(setTopics).catch(() => setTopics([]));
    learnStats().then((s) => setStats(s as Stats)).catch(() => setStats(null));
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!title.trim()) return;
    await createLearnTopic({ title, goal: goal.trim() || undefined });
    setTitle(""); setGoal(""); setShowNew(false);
    load();
  };

  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[820px] mx-auto px-6 sm:px-8 py-8">
          <div className="flex items-center justify-between">
            <div>
              <p className="eyebrow">Spaced repetition</p>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">Learn</h1>
            </div>
            <button onClick={() => setShowNew(!showNew)} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn">
              <Plus size={12} /> New topic
            </button>
          </div>

          {showNew && (
            <div className="mt-4 bg-surface border border-rim rounded-xl p-4 space-y-2">
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Topic title"
                className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-dawn/50" />
              <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Goal (optional)"
                className="w-full bg-elevated/30 border border-rim rounded-lg px-3 py-2 text-sm text-text-primary outline-none focus:border-dawn/50" />
              <button onClick={create} disabled={!title.trim()}
                className="px-4 py-2 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn disabled:opacity-30">Create</button>
            </div>
          )}

          <div className="mt-4 bg-surface border border-rim rounded-xl p-4 flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-text-primary">{stats?.due ?? 0} cards due today</p>
              <p className="text-2xs text-text-muted mt-0.5">
                {stats?.totals ? `${stats.totals.new} new · ${stats.totals.learning} learning · ${stats.totals.mastered} mastered` : "No cards yet"}
              </p>
            </div>
            <Link href="/learn/review"
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-medium bg-dawn/90 text-white hover:bg-dawn">
              <Play size={12} /> Start review
            </Link>
          </div>

          <div className="mt-4 space-y-2">
            {topics.map((t) => (
              <Link key={t.id} href={`/learn/${t.id}`}
                className="flex items-center gap-3 bg-surface border border-rim rounded-xl px-4 py-3 hover:border-dawn/30 transition-colors">
                <GraduationCap size={16} className="text-dawn flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{t.title}</p>
                  {t.summary && <p className="text-2xs text-text-muted truncate">{t.summary}</p>}
                </div>
                <span className="text-2xs text-text-muted flex-shrink-0">{t.level}</span>
              </Link>
            ))}
            {topics.length === 0 && <p className="text-text-muted text-2xs py-6 text-center">No topics yet.</p>}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
