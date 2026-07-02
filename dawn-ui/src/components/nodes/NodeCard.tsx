"use client";

import { useState } from "react";
import { Trash2, Edit2, CheckCircle, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import clsx from "clsx";
import type { DawnNode } from "@/lib/types";

const TYPE_COLORS: Record<string, string> = {
  concept:  "text-blue-400 bg-blue-400/10 border-blue-400/20",
  entity:   "text-dawn bg-dawn/10 border-dawn/20",
  process:  "text-purple-400 bg-purple-400/10 border-purple-400/20",
  fact:     "text-green-400 bg-green-400/10 border-green-400/20",
  memory:   "text-ember bg-ember/10 border-ember/20",
  document: "text-text-secondary bg-surface border-rim",
};

const CONFIDENCE_COLOR = (c: number) =>
  c >= 0.9 ? "text-green-400" : c >= 0.7 ? "text-ember" : "text-red-400";

interface Props {
  node: DawnNode;
  onEdit?: (node: DawnNode) => void;
  onDelete?: (id: string) => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  showReviewActions?: boolean;
}

export default function NodeCard({
  node,
  onEdit,
  onDelete,
  onApprove,
  onReject,
  showReviewActions,
}: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={clsx(
        "bg-surface border rounded-xl p-4 transition-all duration-200 group",
        node.status === "draft"
          ? "border-ember/30 bg-ember/5"
          : "border-rim hover:border-dawn/25",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={clsx(
                "text-[10px] font-mono px-1.5 py-0.5 rounded border",
                TYPE_COLORS[node.type] || TYPE_COLORS.document,
              )}
            >
              {node.type}
            </span>
            {node.status !== "active" && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border text-ember bg-ember/10 border-ember/20">
                {node.status}
              </span>
            )}
          </div>
          <h3 className="text-text-primary font-medium text-sm mt-1.5 leading-snug">
            {node.title}
          </h3>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          {showReviewActions ? (
            <>
              <button
                onClick={() => onApprove?.(node.id)}
                className="w-6 h-6 flex items-center justify-center rounded text-green-400 hover:bg-green-400/10 transition-colors"
                title="Approve"
              >
                <CheckCircle size={13} />
              </button>
              <button
                onClick={() => onReject?.(node.id)}
                className="w-6 h-6 flex items-center justify-center rounded text-red-400 hover:bg-red-400/10 transition-colors"
                title="Reject"
              >
                <XCircle size={13} />
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => onEdit?.(node)}
                className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-dawn hover:bg-dawn/10 transition-colors"
                title="Edit"
              >
                <Edit2 size={12} />
              </button>
              <button
                onClick={() => onDelete?.(node.id)}
                className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-red-400 hover:bg-red-400/10 transition-colors"
                title="Delete"
              >
                <Trash2 size={12} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Body preview */}
      {node.body && (
        <div className="mt-2">
          <p
            className={clsx(
              "text-text-secondary text-xs leading-relaxed",
              !expanded && "line-clamp-2",
            )}
          >
            {node.body}
          </p>
          {node.body.length > 120 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="mt-1 text-text-muted text-[10px] flex items-center gap-0.5 hover:text-dawn transition-colors"
            >
              {expanded ? <><ChevronUp size={10} /> Less</> : <><ChevronDown size={10} /> More</>}
            </button>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between gap-2">
        {/* Tags */}
        <div className="flex flex-wrap gap-1">
          {(node.tags || []).map((tag) => (
            <span
              key={tag}
              className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-elevated text-text-muted border border-rim"
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Confidence */}
        <span
          className={clsx("text-[10px] font-mono flex-shrink-0", CONFIDENCE_COLOR(node.confidence))}
          title={`Confidence: ${Math.round(node.confidence * 100)}%`}
        >
          {Math.round(node.confidence * 100)}%
        </span>
      </div>
    </div>
  );
}
