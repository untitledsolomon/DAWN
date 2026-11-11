"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { GraduationCap, BookOpen, ListChecks } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import { getLearnTopic, learnStats, topicLessons, type LearnTopic } from "@/lib/api";

function Bar({ newC, learnC, masterC }: { newC: number; learnC: number; masterC: number }) {
  const total = newC + learnC + masterC || 1;
  return (
    <div className="flex h-2 rounded-full overflow-hidden bg-elevated">
      <div className="bg-dawn/70" style={{ width: `${(newC / total) * 100}%` }} />
      <div className="bg-amber-500/70" style={{ width: `${(learnC / total) * 100}%` }} />
      <div className="bg-success/80" style={{ width: `${(masterC / total) * 100}%` }} />
    </div>
  );
}

export default function LearnTopicPage() {
  const params = useParams<{ topicId: string }>();
  const id = params.topicId;
  const [topic, setTopic] = useState<LearnTopic | null>(null);
  const [lessons, setLessons] = useState<{ id: string; artifact_id: string; title: string; created_at: string }[]>([]);
  const [stats, setStats] = useState<{ totals?: { new: number; learning: number; mastered: number } } | null>(null);

  useEffect(() => {
    getLearnTopic(id).then(setTopic).catch(() => setTopic(null));
    topicLessons(id).then(setLessons).catch(() => setLessons([]));
    learnStats(id).then((s) => setStats(s as never)).catch(() => setStats(null));
  }, [id]);

  const t = topic;
  return (
    <AppShell>
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[720px] mx-auto px-6 sm:px-8 py-8">
          <Link href="/learn" className="text-2xs text-text-muted hover:text-text-secondary">← Learn</Link>
          <h1 className="text-xl font-semibold tracking-tight text-text-primary mt-2">{t?.title ?? "…"}</h1>
          {t?.goal && <p className="text-text-muted text-sm mt-1">{t.goal}</p>}

          <div className="mt-4 grid grid-cols-2 gap-3">
            <a href={`/canvas?learn_topic=${id}&learn_style=explain`}
              className="flex items-center gap-2 px-4 py-3 rounded-xl bg-dawn/90 text-white text-xs font-medium hover:bg-dawn">
              <GraduationCap size={14} /> Study this
            </a>
            <a href={`/canvas?learn_topic=${id}&learn_style=coach&quiz=1`}
              className="flex items-center gap-2 px-4 py-3 rounded-xl bg-surface border border-rim text-text-secondary text-xs font-medium hover:border-dawn/40">
              <ListChecks size={14} /> Quiz me
            </a>
          </div>

          <div className="mt-5 bg-surface border border-rim rounded-xl p-4">
            <p className="text-xs font-medium text-text-primary mb-2">Progress</p>
            <Bar newC={stats?.totals?.new ?? 0} learnC={stats?.totals?.learning ?? 0} masterC={stats?.totals?.mastered ?? 0} />
            <p className="text-2xs text-text-muted mt-2">
              {stats?.totals?.new ?? 0} new · {stats?.totals?.learning ?? 0} learning · {stats?.totals?.mastered ?? 0} mastered
            </p>
          </div>

          <div className="mt-5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-text-primary mb-2"><BookOpen size={13} /> Lessons</p>
            <div className="space-y-1.5">
              {lessons.map((l) => (
                <a key={l.id} href={`/canvas?id=${l.artifact_id}`}
                  className="block bg-surface border border-rim rounded-lg px-3 py-2 text-xs text-text-secondary hover:border-dawn/30">
                  {l.title}
                </a>
              ))}
              {lessons.length === 0 && <p className="text-2xs text-text-muted">No lessons yet. Start with "Study this".</p>}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
