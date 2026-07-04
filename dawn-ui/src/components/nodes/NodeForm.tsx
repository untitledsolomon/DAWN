"use client";

import { useState, useEffect } from "react";
import { X, Plus } from "lucide-react";
import type { DawnNode, Tag } from "@/lib/types";

import { NodeType, NodeTypeFilter } from "@/types"; // adjust path

const NODE_TYPES: NodeType[] = ["concept", "entity", "process", "fact", "memory", "document"];

interface Props {
  node?: DawnNode | null;
  availableTags: Tag[];
  onSave: (data: Partial<DawnNode> & { tags: string[] }) => Promise<void>;
  onClose: () => void;
}

export default function NodeForm({ node, availableTags, onSave, onClose }: Props) {
  const [title, setTitle] = useState(node?.title || "");
  const [type, setType] = useState(node?.type || "concept");
  const [body, setBody] = useState(node?.body || "");
  const [confidence, setConfidence] = useState(node?.confidence ?? 1.0);
  const [selectedTags, setSelectedTags] = useState<string[]>(node?.tags || []);
  const [newTag, setNewTag] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const isEdit = !!node;

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  };

  const addCustomTag = () => {
    const t = newTag.trim().toLowerCase().replace(/\s+/g, "-");
    if (t && !selectedTags.includes(t)) {
      setSelectedTags((prev) => [...prev, t]);
    }
    setNewTag("");
  };

  const handleSave = async () => {
    if (!title.trim()) { setError("Title is required"); return; }
    setSaving(true);
    setError("");
    try {
      await onSave({ title, type: type as DawnNode["type"], body, confidence, tags: selectedTags });
      onClose();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 bg-canvas/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface border border-rim rounded-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto animate-slide-up shadow-card">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-rim">
          <h2 className="text-text-primary font-semibold text-sm tracking-tight">
            {isEdit ? "Edit Node" : "New Node"}
          </h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-text-muted hover:text-text-primary hover:bg-elevated/60 transition-all"
          >
            <X size={14} />
          </button>
        </div>

        {/* Form */}
        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="text-text-secondary text-xs font-medium block mb-1.5">Title *</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Sentinel Trading Bot"
              className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 transition-colors"
            />
          </div>

          <div>
            <label className="text-text-secondary text-xs font-medium block mb-1.5">Type</label>
            <div className="flex flex-wrap gap-1.5">
              {NODE_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setType(t)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-mono border transition-all ${
                    type === t
                      ? "bg-dawn/15 border-dawn/40 text-dawn"
                      : "bg-elevated/50 border-rim text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-text-secondary text-xs font-medium block mb-1.5">
              Body <span className="text-text-muted">(keep it short — one idea per node)</span>
            </label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              placeholder="What this node represents, in 1-3 sentences..."
              className="w-full bg-elevated/50 border border-rim rounded-lg px-3 py-2 text-text-primary text-sm placeholder:text-text-muted outline-none focus:border-dawn/50 transition-colors resize-none font-sans"
            />
          </div>

          <div>
            <label className="text-text-secondary text-xs font-medium block mb-1.5">Tags</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {availableTags.map((tag) => (
                <button
                  key={tag.id}
                  onClick={() => toggleTag(tag.name)}
                  className={`px-2 py-0.5 rounded-full text-2xs font-mono border transition-all ${
                    selectedTags.includes(tag.name)
                      ? "bg-dawn/15 border-dawn/40 text-dawn"
                      : "bg-elevated/50 border-rim text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {tag.name}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addCustomTag()}
                placeholder="Custom tag..."
                className="flex-1 bg-elevated/50 border border-rim rounded-lg px-3 py-1.5 text-text-primary text-xs placeholder:text-text-muted outline-none focus:border-dawn/50 transition-colors font-mono"
              />
              <button
                onClick={addCustomTag}
                className="px-3 py-1.5 rounded-lg bg-elevated/50 border border-rim text-text-muted hover:text-dawn hover:border-dawn/30 transition-all text-xs"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>

          <div>
            <label className="text-text-secondary text-xs font-medium block mb-1.5">
              Confidence: <span className="font-mono text-dawn">{Math.round(confidence * 100)}%</span>
            </label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.1}
              value={confidence}
              onChange={(e) => setConfidence(Number(e.target.value))}
              className="w-full accent-[#0FA8A6]"
            />
            <div className="flex justify-between text-2xs text-text-muted font-mono mt-0.5">
              <span>uncertain</span><span>certain</span>
            </div>
          </div>

          {error && (
            <p className="text-error text-xs px-3 py-2 rounded-lg bg-error/10 border border-error/20">
              {error}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-rim">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-text-secondary hover:text-text-primary text-sm transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-sm font-medium disabled:opacity-50 transition-all"
          >
            {saving ? "Saving..." : isEdit ? "Save Changes" : "Create Node"}
          </button>
        </div>
      </div>
    </div>
  );
}
