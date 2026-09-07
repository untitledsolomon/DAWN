"use client";

import { useState, useEffect, useCallback } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  listProjects,
  createProject,
  deleteProject,
  getProjectRelated,
} from "@/lib/api";
import type { Project, ProjectRelated } from "@/lib/api";
import {
  FolderKanban,
  Plus,
  Trash2,
  Loader2,
  AlertCircle,
  Database,
  Brain,
  GitBranch,
  MessageSquare,
  X,
  ChevronLeft,
  Tag,
} from "lucide-react";
import clsx from "clsx";

const STATUSES = ["active", "paused", "completed", "cancelled"];
const PRIORITIES = ["low", "medium", "high", "critical"];

const STATUS_COLORS: Record<string, string> = {
  active: "text-dawn bg-dawn/10 border-dawn/20",
  paused: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  completed: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
  cancelled: "text-text-muted bg-elevated/60 border-rim",
};

const PRIORITY_COLORS: Record<string, string> = {
  low: "text-text-muted bg-elevated/60 border-rim",
  medium: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  high: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  critical: "text-ember bg-ember/10 border-ember/20",
};

const SECTION_ICONS: Record<string, React.ElementType> = {
  artifacts: Database,
  memories: Brain,
  nodes: GitBranch,
  sessions: MessageSquare,
};

function ProjectsContent() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [formOpen, setFormOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("active");
  const [priority, setPriority] = useState("medium");
  const [tagsInput, setTagsInput] = useState("");

  // Detail state
  const [selected, setSelected] = useState<ProjectRelated | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const fetchProjects = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      console.error("[Projects] Failed to load:", err);
      setError("Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleDelete = async (id: string) => {
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
      if (selected?.project.id === id) setSelected(null);
    } catch (err) {
      console.error("[Projects] Failed to delete:", err);
    }
  };

  const handleCreate = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setFormError(null);
    try {
      const tags = tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
        status,
        priority,
        tags: tags.length ? tags : undefined,
      });
      setName("");
      setDescription("");
      setStatus("active");
      setPriority("medium");
      setTagsInput("");
      setFormOpen(false);
      await fetchProjects();
    } catch (err) {
      console.error("[Projects] Failed to create:", err);
      setFormError("Failed to create project");
    } finally {
      setCreating(false);
    }
  };

  const handleSelect = async (project: Project) => {
    setSelected(null);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const related = await getProjectRelated(project.id);
      setSelected(related);
    } catch (err) {
      console.error("[Projects] Failed to load related:", err);
      setDetailError("Failed to load related content");
    } finally {
      setDetailLoading(false);
    }
  };

  const inputClass =
    "w-full bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all";

  return (
    <div className="flex h-full">
      {/* Main list */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 border-b border-rim px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-text-primary text-sm font-semibold">Projects</h1>
              <p className="text-text-muted text-2xs mt-0.5">
                Define goals and see everything DAWN knows about them
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-text-muted text-2xs font-mono">{projects.length} projects</span>
              <button
                onClick={() => setFormOpen((v) => !v)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all shadow-soft"
              >
                <Plus size={12} />
                New Project
              </button>
            </div>
          </div>

          {/* Create form */}
          {formOpen && (
            <div className="rounded-xl bg-surface border border-rim shadow-soft p-4 space-y-3 animate-fade-in">
              <div className="flex items-center justify-between">
                <h3 className="text-text-primary text-xs font-semibold flex items-center gap-1.5">
                  <FolderKanban size={13} className="text-dawn" />
                  Define a new project / goal
                </h3>
                <button
                  onClick={() => setFormOpen(false)}
                  className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
                >
                  <X size={12} />
                </button>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="sm:col-span-2">
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Name
                  </label>
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Marketing X"
                    className={inputClass}
                  />
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="What is this project about?"
                    rows={2}
                    className={clsx(inputClass, "resize-none")}
                  />
                </div>
                <div>
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Status
                  </label>
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className={inputClass}
                  >
                    {STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Priority
                  </label>
                  <select
                    value={priority}
                    onChange={(e) => setPriority(e.target.value)}
                    className={inputClass}
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-text-muted text-2xs font-medium uppercase tracking-wider mb-1">
                    Tags (comma-separated)
                  </label>
                  <input
                    value={tagsInput}
                    onChange={(e) => setTagsInput(e.target.value)}
                    placeholder="growth, q3, research"
                    className={inputClass}
                  />
                </div>
              </div>
              {formError && <p className="text-ember text-2xs">{formError}</p>}
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setFormOpen(false)}
                  className="px-3 py-1.5 rounded-lg border border-rim text-text-muted hover:text-text-secondary text-xs transition-all"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={creating || !name.trim()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn text-white text-xs font-medium hover:bg-dawn/90 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {creating ? <Loader2 size={12} className="animate-spin" /> : <Plus size={12} />}
                  Create
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="text-dawn animate-spin" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <AlertCircle size={18} className="text-ember" />
              <p className="text-text-muted text-sm">{error}</p>
              <button
                onClick={fetchProjects}
                className="px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
              >
                Retry
              </button>
            </div>
          ) : projects.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <FolderKanban size={24} className="text-text-muted/50" />
              <p className="text-text-muted text-sm">
                No projects yet. Create one to start tracking a goal.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {projects.map((project) => (
                <button
                  key={project.id}
                  onClick={() => handleSelect(project)}
                  className="text-left p-3 rounded-xl bg-surface border border-rim hover:border-dawn/30 transition-all group shadow-soft"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center border text-dawn bg-dawn/10 border-dawn/20">
                      <FolderKanban size={14} />
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(project.id);
                      }}
                      className="w-6 h-6 flex items-center justify-center rounded text-text-muted opacity-0 group-hover:opacity-100 hover:text-ember transition-all"
                      title="Delete"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                  <h3 className="text-text-primary text-xs font-medium truncate">{project.name}</h3>
                  {project.description && (
                    <p className="text-text-muted text-2xs mt-0.5 line-clamp-2">{project.description}</p>
                  )}
                  <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                    <span
                      className={clsx(
                        "px-1.5 py-0.5 rounded border text-2xs capitalize",
                        STATUS_COLORS[project.status] || "text-text-muted bg-elevated/60 border-rim"
                      )}
                    >
                      {project.status}
                    </span>
                    <span
                      className={clsx(
                        "px-1.5 py-0.5 rounded border text-2xs capitalize",
                        PRIORITY_COLORS[project.priority] || "text-text-muted bg-elevated/60 border-rim"
                      )}
                    >
                      {project.priority}
                    </span>
                    {project.tags && project.tags.length > 0 && (
                      <span className="flex items-center gap-1 text-text-muted text-2xs">
                        <Tag size={9} />
                        {project.tags.length}
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Detail panel */}
      {(selected || detailLoading) && (
        <div className="w-96 border-l border-rim bg-surface/80 backdrop-blur-sm overflow-y-auto flex-shrink-0 hidden lg:block">
          <div className="p-4">
            {detailLoading ? (
              <div className="flex items-center justify-center py-16">
                <Loader2 size={18} className="text-dawn animate-spin" />
              </div>
            ) : detailError ? (
              <div className="flex flex-col items-center justify-center py-16 gap-2">
                <AlertCircle size={16} className="text-ember" />
                <p className="text-text-muted text-xs">{detailError}</p>
              </div>
            ) : selected ? (
              <>
                {/* Header */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center border text-dawn bg-dawn/10 border-dawn/20">
                      <FolderKanban size={14} />
                    </div>
                    <div>
                      <h3 className="text-text-primary text-sm font-medium">{selected.project.name}</h3>
                      <span className="text-text-muted text-2xs capitalize">{selected.project.status}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelected(null)}
                    className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
                  >
                    <X size={12} />
                  </button>
                </div>

                {selected.project.description && (
                  <p className="text-text-muted text-xs mb-3">{selected.project.description}</p>
                )}

                {/* Tags */}
                {selected.project.tags && selected.project.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-4">
                    {selected.project.tags.map((tag) => (
                      <span
                        key={tag}
                        className="px-1.5 py-0.5 rounded bg-elevated/60 border border-rim text-text-muted text-2xs"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {/* Related sections */}
                {[
                  { key: "artifacts", label: "Artifacts", items: selected.artifacts, typeKey: "type" },
                  { key: "memories", label: "Memories", items: selected.memories, typeKey: "fact_type" },
                  { key: "nodes", label: "Nodes", items: selected.nodes, typeKey: "type" },
                  { key: "sessions", label: "Sessions", items: selected.sessions, typeKey: null },
                ].map(({ key, label, items, typeKey }) => {
                  const Icon = SECTION_ICONS[key] || Database;
                  return (
                    <div key={key} className="mb-4">
                      <h4 className="flex items-center gap-1.5 text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">
                        <Icon size={11} />
                        {label}
                        <span className="text-text-muted/60 font-mono">{items.length}</span>
                      </h4>
                      {items.length === 0 ? (
                        <p className="text-text-muted/60 text-2xs">Nothing linked yet</p>
                      ) : (
                        <ul className="space-y-1.5">
                          {items.map((item) => (
                            <li
                              key={item.id}
                              className="rounded-lg border border-rim bg-elevated/40 px-2.5 py-1.5"
                            >
                              <p className="text-text-primary text-xs truncate">{item.title}</p>
                              {typeKey && item[typeKey as keyof typeof item] ? (
                                <p className="text-text-muted text-2xs capitalize">
                                  {String(item[typeKey as keyof typeof item])}
                                </p>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                })}
              </>
            ) : null}
          </div>
        </div>
      )}

      {/* Mobile detail — full screen overlay */}
      {selected && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setSelected(null)} />
          <div className="absolute inset-y-0 right-0 w-full max-w-md bg-surface border-l border-rim overflow-y-auto shadow-soft">
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={() => setSelected(null)}
                  className="flex items-center gap-1 text-text-muted hover:text-text-secondary text-xs"
                >
                  <ChevronLeft size={14} />
                  Back
                </button>
                <button
                  onClick={() => handleDelete(selected.project.id)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-rim text-text-muted hover:text-ember hover:border-ember/30 transition-all text-2xs"
                >
                  <Trash2 size={10} />
                  Delete
                </button>
              </div>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-8 h-8 rounded-lg flex items-center justify-center border text-dawn bg-dawn/10 border-dawn/20">
                  <FolderKanban size={14} />
                </div>
                <div>
                  <h3 className="text-text-primary text-sm font-medium">{selected.project.name}</h3>
                  <span className="text-text-muted text-2xs capitalize">{selected.project.status}</span>
                </div>
              </div>
              {selected.project.description && (
                <p className="text-text-muted text-xs mb-3">{selected.project.description}</p>
              )}
              {selected.project.tags && selected.project.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-4">
                  {selected.project.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-1.5 py-0.5 rounded bg-elevated/60 border border-rim text-text-muted text-2xs"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {[
                { key: "artifacts", label: "Artifacts", items: selected.artifacts, typeKey: "type" },
                { key: "memories", label: "Memories", items: selected.memories, typeKey: "fact_type" },
                { key: "nodes", label: "Nodes", items: selected.nodes, typeKey: "type" },
                { key: "sessions", label: "Sessions", items: selected.sessions, typeKey: null },
              ].map(({ key, label, items, typeKey }) => {
                const Icon = SECTION_ICONS[key] || Database;
                return (
                  <div key={key} className="mb-4">
                    <h4 className="flex items-center gap-1.5 text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">
                      <Icon size={11} />
                      {label}
                      <span className="text-text-muted/60 font-mono">{items.length}</span>
                    </h4>
                    {items.length === 0 ? (
                      <p className="text-text-muted/60 text-2xs">Nothing linked yet</p>
                    ) : (
                      <ul className="space-y-1.5">
                        {items.map((item) => (
                          <li
                            key={item.id}
                            className="rounded-lg border border-rim bg-elevated/40 px-2.5 py-1.5"
                          >
                            <p className="text-text-primary text-xs truncate">{item.title}</p>
                            {typeKey && item[typeKey as keyof typeof item] ? (
                              <p className="text-text-muted text-2xs capitalize">
                                {String(item[typeKey as keyof typeof item])}
                              </p>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  return (
    <AppShell>
      <ProjectsContent />
    </AppShell>
  );
}
