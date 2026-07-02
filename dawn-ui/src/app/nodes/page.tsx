"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Search, RefreshCw } from "lucide-react";
import Sidebar from "@/components/layout/Sidebar";
import NodeCard from "@/components/nodes/NodeCard";
import NodeForm from "@/components/nodes/NodeForm";
import { listNodes, searchNodes, listTags, createNode, updateNode, deleteNode } from "@/lib/api";
import type { DawnNode, Tag } from "@/lib/types";

const NODE_TYPES = ["all", "concept", "entity", "process", "fact", "memory", "document"];

export default function NodesPage() {
  const [nodes, setNodes] = useState<DawnNode[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [tagFilter, setTagFilter] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingNode, setEditingNode] = useState<DawnNode | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nodeList, tagList] = await Promise.all([
        query
          ? searchNodes(query, 50)
          : listNodes({
              type: typeFilter !== "all" ? typeFilter : undefined,
              tag: tagFilter || undefined,
              limit: 100,
            }),
        listTags(),
      ]);
      setNodes(nodeList);
      setTags(tagList);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [query, typeFilter, tagFilter]);

  useEffect(() => { load(); }, [load]);

  // Debounce search
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

  return (
    <div className="flex h-screen">
      <Sidebar />

      <main className="flex-1 ml-14 flex flex-col min-h-0">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm">Knowledge Base</h1>
            <p className="text-text-muted text-xs">{nodes.length} nodes</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={load}
              className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-dawn hover:bg-dawn/10 transition-all"
            >
              <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            </button>
            <button
              onClick={() => { setEditingNode(null); setShowForm(true); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-abyss text-xs font-medium transition-all"
            >
              <Plus size={13} /> New Node
            </button>
          </div>
        </header>

        <div className="dawn-line flex-shrink-0" />

        {/* Filters */}
        <div className="px-6 py-3 border-b border-rim flex items-center gap-3 flex-shrink-0 flex-wrap">
          {/* Search */}
          <div className="flex items-center gap-2 bg-surface border border-rim rounded-lg px-3 py-1.5 flex-1 min-w-48 max-w-sm focus-within:border-dawn/50 transition-colors">
            <Search size={13} className="text-text-muted flex-shrink-0" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search nodes..."
              className="bg-transparent text-text-primary text-xs placeholder:text-text-muted outline-none w-full"
            />
          </div>

          {/* Type filter */}
          <div className="flex gap-1 flex-wrap">
            {NODE_TYPES.map((t) => (
              <button
                key={t}
                onClick={() => setTypeFilter(t)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-mono border transition-all ${
                  typeFilter === t
                    ? "bg-dawn/15 border-dawn/40 text-dawn"
                    : "bg-surface border-rim text-text-muted hover:text-text-secondary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Tag filter */}
          <select
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
            className="bg-surface border border-rim rounded-lg px-2.5 py-1.5 text-text-secondary text-xs outline-none focus:border-dawn/50 transition-colors"
          >
            <option value="">All tags</option>
            {tags.map((t) => (
              <option key={t.id} value={t.name}>{t.name}</option>
            ))}
          </select>
        </div>

        {/* Node grid */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
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
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
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
      </main>

      {/* Form modal */}
      {showForm && (
        <NodeForm
          node={editingNode}
          availableTags={tags}
          onSave={handleSave}
          onClose={() => { setShowForm(false); setEditingNode(null); }}
        />
      )}
    </div>
  );
}
