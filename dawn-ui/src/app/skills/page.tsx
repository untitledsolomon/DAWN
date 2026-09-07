"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import AppShell from "@/components/layout/AppShell";
import { listSkills, installSkill, installEccSkill, listEccSkills } from "@/lib/api";
import type { InstalledSkill } from "@/lib/api";
import { Package, Plus, Search, Loader2, Check, AlertCircle, Link2, BookOpen } from "lucide-react";

const TYPE_COLORS: Record<string, string> = {
  tool: "text-dawn bg-dawn/10 border-dawn/20",
  prompt: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  agent: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
  workflow: "text-violet-400 bg-violet-400/10 border-violet-400/20",
};

const displayName = (name: string) => name.replace(/^skill_/, "");

function SkillsContent() {
  const [skills, setSkills] = useState<InstalledSkill[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // URL install state
  const [repoUrl, setRepoUrl] = useState("");
  const [installingUrl, setInstallingUrl] = useState(false);
  const [urlMessage, setUrlMessage] = useState<{ ok: boolean; text: string } | null>(null);

  // ECC state
  const [eccQuery, setEccQuery] = useState("");
  const [eccSkills, setEccSkills] = useState<string[]>([]);
  const [eccLoading, setEccLoading] = useState(false);
  const [eccError, setEccError] = useState<string | null>(null);
  const [installingEcc, setInstallingEcc] = useState<string | null>(null);
  const [eccInstalled, setEccInstalled] = useState<string | null>(null);

  const fetchSkills = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listSkills();
      setSkills(data);
      setError(null);
    } catch (err) {
      console.error("[Skills] Failed to load:", err);
      setError("Failed to load installed skills");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // Debounced ECC search
  useEffect(() => {
    if (!eccQuery.trim()) {
      setEccSkills([]);
      setEccError(null);
      return;
    }
    let cancelled = false;
    setEccLoading(true);
    const timer = setTimeout(async () => {
      try {
        const data = await listEccSkills(eccQuery.trim());
        if (!cancelled) {
          setEccSkills(data.skills);
          setEccError(null);
        }
      } catch (err) {
        if (!cancelled) {
          console.error("[Skills] ECC search failed:", err);
          setEccError("Failed to search ECC library");
          setEccSkills([]);
        }
      } finally {
        if (!cancelled) setEccLoading(false);
      }
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [eccQuery]);

  const handleInstallUrl = async () => {
    const url = repoUrl.trim();
    if (!url) return;
    setInstallingUrl(true);
    setUrlMessage(null);
    try {
      const res = await installSkill(url);
      setUrlMessage({ ok: true, text: res.message || `Installed ${res.skill_name || "skill"}` });
      setRepoUrl("");
      await fetchSkills();
    } catch (err) {
      console.error("[Skills] Install from URL failed:", err);
      setUrlMessage({ ok: false, text: err instanceof Error ? err.message : "Install failed" });
    } finally {
      setInstallingUrl(false);
    }
  };

  // ECC install
  const handleInstallEcc = async (skillName: string) => {
    setInstallingEcc(skillName);
    setEccInstalled(null);
    try {
      await installEccSkill(skillName);
      setEccInstalled(skillName);
      await fetchSkills();
    } catch (err) {
      console.error("[Skills] ECC install failed:", err);
      setEccError(err instanceof Error ? err.message : "Install failed");
    } finally {
      setInstallingEcc(null);
    }
  };

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 border-b border-rim px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-text-primary text-sm font-semibold">Skills</h1>
              <p className="text-text-muted text-2xs mt-0.5">
                Installed skills and the ECC library
              </p>
            </div>
            <span className="text-text-muted text-2xs font-mono">{skills.length} installed</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          {/* Installed skills */}
          <section>
            <h2 className="text-text-primary text-xs font-semibold mb-3 flex items-center gap-1.5">
              <Package size={13} className="text-dawn" />
              Installed Skills
            </h2>
            {loading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 size={20} className="text-dawn animate-spin" />
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16">
                <AlertCircle size={18} className="text-ember" />
                <p className="text-text-muted text-sm">{error}</p>
                <button
                  onClick={fetchSkills}
                  className="px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
                >
                  Retry
                </button>
              </div>
            ) : skills.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-16 rounded-xl border border-dashed border-rim">
                <Package size={24} className="text-text-muted/50" />
                <p className="text-text-muted text-sm">No skills installed yet.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {skills.map((skill) => {
                  const colorClass =
                    TYPE_COLORS[skill.type] || "text-text-muted bg-elevated/60 border-rim";
                  return (
                    <div
                      key={skill.name}
                      className="p-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 transition-all"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="text-text-primary text-xs font-medium truncate">
                          {displayName(skill.name)}
                        </h3>
                        <span className={`flex-shrink-0 px-1.5 py-0.5 rounded border text-2xs capitalize ${colorClass}`}>
                          {skill.type}
                        </span>
                      </div>
                      {skill.description && (
                        <p className="text-text-muted text-2xs mt-0.5 line-clamp-2">
                          {skill.description}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {/* Install from URL */}
          <section className="rounded-xl bg-surface border border-rim p-4">
            <h2 className="text-text-primary text-xs font-semibold mb-1 flex items-center gap-1.5">
              <Link2 size={13} className="text-dawn" />
              Install from URL
            </h2>
            <p className="text-text-muted text-2xs mb-3">
              Paste a repo URL or raw file link to install a skill.
            </p>
            <div className="flex items-center gap-2">
              <input
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleInstallUrl();
                }}
                placeholder="https://github.com/user/repo or raw file link..."
                className="flex-1 bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all"
              />
              <button
                onClick={handleInstallUrl}
                disabled={installingUrl || !repoUrl.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-abyss text-xs font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                {installingUrl ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                Install
              </button>
            </div>
            {urlMessage && (
              <p
                className={`mt-2 text-2xs flex items-center gap-1 ${
                  urlMessage.ok ? "text-emerald-400" : "text-ember"
                }`}
              >
                {urlMessage.ok ? <Check size={11} /> : <AlertCircle size={11} />}
                {urlMessage.text}
              </p>
            )}
          </section>

          {/* ECC library */}
          <section className="rounded-xl bg-surface border border-rim p-4">
            <h2 className="text-text-primary text-xs font-semibold mb-1 flex items-center gap-1.5">
              <BookOpen size={13} className="text-dawn" />
              Browse ECC Library
            </h2>
            <p className="text-text-muted text-2xs mb-3">
              Search and install skills from the ECC library.
            </p>
            <div className="flex-1 relative mb-3">
              <Search
                size={12}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-muted"
              />
              <input
                value={eccQuery}
                onChange={(e) => setEccQuery(e.target.value)}
                placeholder="Search ECC skills..."
                className="w-full bg-elevated/60 border border-rim rounded-lg pl-7 pr-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all"
              />
            </div>

            {eccLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 size={16} className="text-dawn animate-spin" />
              </div>
            ) : eccError ? (
              <p className="text-ember text-2xs flex items-center gap-1">
                <AlertCircle size={11} />
                {eccError}
              </p>
            ) : !eccQuery.trim() ? (
              <p className="text-text-muted text-2xs py-4 text-center">
                Type a query to search the ECC library.
              </p>
            ) : eccSkills.length === 0 ? (
              <p className="text-text-muted text-2xs py-4 text-center">
                No skills match your search.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {eccSkills.map((skillName) => {
                  const installed = skills.some((s) => s.name === skillName);
                  return (
                    <li
                      key={skillName}
                      className="flex items-center justify-between gap-2 p-2 rounded-lg border border-rim bg-elevated/40"
                    >
                      <span className="text-text-primary text-xs font-mono truncate">
                        {displayName(skillName)}
                      </span>
                      {installed ? (
                        <span className="flex items-center gap-1 text-emerald-400 text-2xs flex-shrink-0">
                          <Check size={11} />
                          Installed
                        </span>
                      ) : (
                        <button
                          onClick={() => handleInstallEcc(skillName)}
                          disabled={installingEcc !== null}
                          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-dawn/10 text-dawn text-2xs font-medium hover:bg-dawn/20 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex-shrink-0"
                        >
                          {installingEcc === skillName ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <Plus size={11} />
                          )}
                          Install
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

export default function SkillsPage() {
  return (
    <AppShell>
      <SkillsContent />
    </AppShell>
  );
}
