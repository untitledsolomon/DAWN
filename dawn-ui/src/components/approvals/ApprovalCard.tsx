"use client";

import { Check, X, CheckCircle2 } from "lucide-react";
import clsx from "clsx";
import Pill from "@/components/ui/Pill";
import { timeAgo } from "@/lib/format";

export type ApprovalKind = "node" | "decision";

export interface ApprovalItem {
  id: string;
  kind: ApprovalKind;
  category: string;       // e.g. "NODE · KNOWLEDGE" or "DECISION"
  title: string;
  description: string;
  impact: "sandboxed" | "production";
  created_at: string;
}

interface Props {
  item: ApprovalItem;
  resolved?: boolean;
  onApprove?: (item: ApprovalItem) => void;
  onReject?: (item: ApprovalItem) => void;
}

/**
 * Approval card — category pill, title, one-line description, a clearly
 * separated impact row, and Reject / Approve actions. Resolved cards render at
 * reduced opacity with a checkmark badge instead of buttons (kept as history).
 */
export default function ApprovalCard({ item, resolved = false, onApprove, onReject }: Props) {
  return (
    <div className={clsx("card approval", resolved && "resolved")}>
      <div className="approval-main">
        <Pill tone="neutral" className="mb-1.5">{item.category}</Pill>
        <div className="approval-title">{item.title}</div>
        <div className="approval-desc">{item.description}</div>

        {/* Impact row — its own visual weight, separated from buttons */}
        <div className="mt-2.5">
          <span
            className={clsx(
              "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[8px] border text-2xs font-medium",
              item.impact === "production"
              ? "border-amber/40 bg-amber/5 text-amber"
              : "border-rim bg-elevated/40 text-text-secondary"
            )}
          >
            <span className={clsx("w-1.5 h-1.5 rounded-full", item.impact === "production" ? "bg-amber" : "bg-text-muted")} />
            {item.impact === "production"
              ? "production — writes to live data"
              : "sandboxed — no production impact"}
          </span>
        </div>
      </div>

      <div className="approval-actions">
        {resolved ? (
          <span className="check" title="Resolved">
            <CheckCircle2 size={14} />
          </span>
        ) : (
          <>
            <span className="mono flex-none">{timeAgo(item.created_at)}</span>
            <button onClick={() => onReject?.(item)} className="btn" title="Reject">
              <X size={11} /> Reject
            </button>
            <button onClick={() => onApprove?.(item)} className="btn primary" title="Approve">
              <Check size={11} /> Approve
            </button>
          </>
        )}
      </div>
    </div>
  );
}
