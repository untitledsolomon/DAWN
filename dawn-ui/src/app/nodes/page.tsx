"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Search, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import NodeCard from "@/components/nodes/NodeCard";
import NodeForm from "@/components/nodes/NodeForm";
import { listNodes, countNodes, searchNodes, listTags, createNode, updateNode, deleteNode } from "@/lib/api";
import type { DawnNode, Tag } from "@/lib/types";

import { NodeType, NodeTypeFilter } from "@/lib/types"; // adjust path

const NODE_TYPES: NodeType[] = ["concept", "entity", "process", "fact", "memory", "document"];
const PAGE_SIZE = 24;
const MAX_VISIBLE_PAGES = 7;

export default function NodesPage() {
  const [nodes, setNodes] = useState<DawnNode[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingNode, setEditingNode] = useState<DawnNode | null>(null);
  const [page, setPage] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));

  // Reset to page 0 when filters change
  useEffect(() => {
    setPage(0);
  }, [query, typeFilter, tagFilter]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nodeList, tagList, count] = await Promise.all([
        query
          ? searchNodes(query, 50)
          : listNodes({
              type: typeFilter !== "all" ? typeFilter : undefined,
              tag: tagFilter || undefined,
              limit: PAGE_SIZE,
              offset: page * PAGE_SIZE,
            }),
        listTags(),
        query
          ? Promise.resolve(0)
          : countNodes({
              type: typeFilter !== "all" ? typeFilter : undefined,
              tag: tagFilter || undefined,
            }),
      ]);
      setNodes(nodeList);
      setTags(tagList);
      setTotalCount(count);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [query, typeFilter, tagFilter, page]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [query, load]);

  const handleSave = async (data: Partial<DawnNode> & { tags: string[] }) => {
    if (editingNode) {
      await updateNode(editingNode.id, data);
    } else {
      await createNode(data);
    }
    setShowForm(false);
    setEditingNode(null);
    load();
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this node? Edges connected to it will also be removed.")) return;
    await deleteNode(id);
    setNodes((prev) => prev.filter((n) => n.id !== id));
  };

  const handleEdit = (node: DawnNode) => {
    setEditingNode(node);
    setShowForm(true);
  };

  // Build pagination window
  const getPageWindow = (): (number | "ellipsis")[] => {
    if (totalPages <= MAX_VISIBLE_PAGES) {
      return Array.from({ length: totalPages }, (_, i) => i);
    }
    const half = Math.floor(MAX_VISIBLE_PAGES / 2);
    let start = Math.max(0, page - half);
    let end = Math.min(totalPages - 1, page + half);
    if (page - half < 0) {
      end = MAX_VISIBLE_PAGES - 1;
    }
    if (page + half >= totalPages) {
      start = totalPages - MAX_VISIBLE_PAGES;
    }
    const pages: (number | "ellipsis")[] = [];
    if (start > 0) {
      pages.push(0);
      if (start > 1) pages.push("ellipsis");
    }
    for (let i = start; i <= end; i++) pages.push(i);
    if (end < totalPages - 1) {
      if (end < totalPages - 2) pages.push("ellipsis");
      pages.push(totalPages - 1);
    }
    return pages;
  };

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        {/* Header */}
        <header className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-rim flex-shrink-0">
          <div className="min-w-0">
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Knowledge Base</h1>
            <p className="text-text-muted text-2xs">
              {totalCount > 0
                ? `${totalCount} nodes · Page ${page + 1} of ${totalPages}`
                : `${nodes.length} nodes`}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={load}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => { setEditingNode(null); setShowForm(true); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all"
            >
              <Plus size={13} /> <span className="hidden xs:inline">New Node</span>
            </button>
          </div>
        </header>

        {/* Filters */}
        <div className="px-4 sm:px-6 py-2.5 border-b border-rim flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-3 flex-shrink-0">
          <div className="flex items-center gap-2 bg-surface border border-rim rounded-lg px-3 py-1.5 w-full sm:w-auto sm:flex-1 sm:min-w-48 sm:max-w-sm focus-within:border-dawn/50 transition-colors">
            <Search size={13} className="text-text-muted flex-shrink-0" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search nodes..."
              className="bg-transparent text-text-primary text-xs placeholder:text-text-muted outline-none w-full"
            />
          </div>

          <div className="flex gap-1 flex-wrap">
            {NODE_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-2 py-1 rounded-lg text-2xs font-mono border transition-all ${
                  typeFilter === t
                    ? "bg-dawn/15 border-dawn/40 text-dawn"
                    : "bg-surface border-rim text-text-muted hover:text-text-secondary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="bg-surface border border-rim rounded-lg px-2.5 py-1.5 text-text-secondary text-xs outline-none focus:border-dawn/50 transition-colors w-full sm:w-auto"
          >
            <option value="">All tags</option>
            {tags.map((t) => (
              <option key={t.id} value={t.name}>{t.name}</option>
            ))}
          </select>
        </div>

        {/* Node grid */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center h-48">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 gap-3">
              <p className="text-text-muted text-sm">No nodes found</p>
              <button
                onClick={() => { setEditingNode(null); setShowForm(true); }}
                className="text-dawn text-xs hover:underline"
              >
                Create your first node →
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
              {nodes.map((node) => (
                <NodeCard
                  key={node.id}
                  node={node}
                  onEdit={handleEdit}
                  onDelete={handleDelete}
                />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-1 px-4 sm:px-6 py-3 border-t border-rim flex-shrink-0">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronLeft size={14} />
            </button>
            {getPageWindow().map((p, i) =>
              p === "ellipsis" ? (
                <span key={`e-${i}`} className="w-7 h-7 flex items-center justify-center text-text-muted text-xs">
                  …
                </span>
              ) : (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-7 h-7 flex items-center justify-center rounded-lg text-xs font-medium transition-all ${
                    p === page
                      ? "bg-dawn/15 text-dawn"
                      : "text-text-muted hover:text-dawn hover:bg-dawn/10"
                  }`}
                >
                  {p + 1}
                </button>
              )
            )}
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 disabled:opacity-30 disabled:cursor-not-allowed transition-all"
            >
              <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      {showForm && (
        <NodeForm
          node={editingNode}
          availableTags={tags}
          onSave={handleSave}
          onClose={() => { setShowForm(false); setEditingNode(null); }}
        />
      )}
    </AppShell>
  );
}
