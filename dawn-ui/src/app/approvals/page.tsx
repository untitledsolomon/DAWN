"use client";

import { useEffect, useState, useCallback } from "react";
import AppShell from "@/components/layout/AppShell";
import ApprovalCard, { type ApprovalItem } from "@/components/approvals/ApprovalCard";
import {
  getPendingNodes,
  approveNode,
  rejectNode,
  listDecisionLog,
  approveDecision,
  listPendingActions,
  approvePendingAction,
  rejectPendingAction,
  type DecisionLogEntry,
  type PendingAction,
} from "@/lib/api";
import type { DawnNode } from "@/lib/types";

const DECISION_BY = "approvals-page";

export default function ApprovalsPage() {
  const [pending, setPending] = useState<ApprovalItem[]>([]);
  const [resolved, setResolved] = useState<ApprovalItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nodes, decisions, actions] = await Promise.all([
        getPendingNodes().catch(() => [] as DawnNode[]),
        listDecisionLog({ limit: 100 })
          .then((d) => d.filter((x) => !x.human_decision))
          .catch(() => [] as DecisionLogEntry[]),
        listPendingActions("pending").catch(() => [] as PendingAction[]),
      ]);

      const nodeItems: ApprovalItem[] = nodes.map((n) => ({
        id: n.id,
        kind: "node",
        category: `NODE · ${(n.type || "knowledge").toUpperCase()}`,
        title: n.title,
        description: "Allow this node to join the active knowledge graph.",
        impact: "sandboxed",
        created_at: n.created_at,
      }));

      const decisionItems: ApprovalItem[] = decisions.map((d) => ({
        id: d.id,
        kind: "decision",
        category: "DECISION",
        title: d.workflow_name.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()),
        description: d.llm_explanation || "Approve the recommendation generated from the latest signals.",
        impact: "production",
        created_at: d.created_at,
      }));

      const actionItems: ApprovalItem[] = actions.map((a) => ({
        id: a.id,
        kind: "mcp_action",
        category: a.server_id ? "MCP ACTION" : "ACTION",
        title: a.tool_name,
        description: `Mutating action queued for approval. Args: ${JSON.stringify(a.tool_args)}`,
        impact: "production",
        created_at: a.created_at,
      }));

      setPending([...nodeItems, ...decisionItems, ...actionItems]);
    } catch (err: any) {
      console.error("[Approvals] Failed to load:", err);
      setError(err?.message || "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = (item: ApprovalItem) => {
    setPending((prev) => prev.filter((p) => p.id !== item.id));
    setResolved((prev) => [item, ...prev]);
  };

  const handleApprove = async (item: ApprovalItem) => {
    try {
      if (item.kind === "node") {
        await approveNode(item.id);
      } else if (item.kind === "mcp_action") {
        await approvePendingAction(item.id);
      } else {
        await approveDecision(item.id, { decision: "approved", by: DECISION_BY });
      }
      resolve(item);
    } catch (err: any) {
      console.error("[Approvals] Approve failed:", err);
      alert(`Failed to approve: ${err?.message || "unknown error"}`);
    }
  };

  const handleReject = async (item: ApprovalItem) => {
    try {
      if (item.kind === "node") {
        await rejectNode(item.id);
      } else if (item.kind === "mcp_action") {
        await rejectPendingAction(item.id);
      } else {
        await approveDecision(item.id, { decision: "rejected", by: DECISION_BY });
      }
      resolve(item);
    } catch (err: any) {
      console.error("[Approvals] Reject failed:", err);
      alert(`Failed to reject: ${err?.message || "unknown error"}`);
    }
  };

  const handleApproveAll = async () => {
    if (!confirm(`Approve all ${pending.length} pending item(s)? This fires real mutations.`)) return;
    setApprovingAll(true);
    for (const item of [...pending]) {
      try {
        if (item.kind === "node") {
          await approveNode(item.id);
        } else if (item.kind === "mcp_action") {
          await approvePendingAction(item.id);
        } else {
          await approveDecision(item.id, { decision: "approved", by: DECISION_BY });
        }
        resolve(item);
      } catch (err) {
        console.error("[Approvals] Approve-all failed on:", item.id, err);
      }
    }
    setApprovingAll(false);
  };

  return (
    <AppShell>
      <div className="h-full overflow-y-auto">
        <div className="max-w-[1180px] mx-auto px-6 sm:px-7 py-6 pb-10">
          {/* Header */}
          <div className="flex items-end justify-between mb-4">
            <div>
              <p className="eyebrow">Review queue</p>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary mt-1">Approvals</h1>
              <p className="subtitle">
                Actions waiting for a human decision. Original approval controls remain available in their source pages.
              </p>
            </div>
            <div className="flex items-center gap-2.5">
              <span className="mono">{pending.length} pending</span>
              <button
                onClick={handleApproveAll}
                disabled={pending.length === 0 || approvingAll}
                className="btn outline-teal"
              >
                {approvingAll ? "Approving…" : "Approve all"}
              </button>
            </div>
          </div>

          {error && <p className="text-ember text-xs mb-3">{error}</p>}

          {/* Pending list */}
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-5 h-5 border-2 border-rim border-t-dawn rounded-full animate-spin" />
            </div>
          ) : pending.length === 0 ? (
            <div className="card p-8 text-center text-text-muted text-sm">
              Nothing waiting for your approval.
            </div>
          ) : (
            <div className="space-y-2.5">
              {pending.map((item) => (
                <ApprovalCard
                  key={item.id}
                  item={item}
                  onApprove={handleApprove}
                  onReject={handleReject}
                />
              ))}
            </div>
          )}

          {/* Resolved history */}
          {resolved.length > 0 && (
            <>
              <div className="mt-6 mb-2">
                <p className="eyebrow">Resolved</p>
              </div>
              <div className="space-y-2.5">
                {resolved.map((item) => (
                  <ApprovalCard key={item.id} item={item} resolved />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </AppShell>
  );
}
