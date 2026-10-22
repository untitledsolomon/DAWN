"use client";

import { useCallback, useEffect, useState } from "react";
import { ShieldCheck, ShieldX, Loader2 } from "lucide-react";
import type { ApprovalBlock as ApprovalBlockT } from "@/lib/ui/schema";
import { approvePendingAction, rejectPendingAction, listPendingActions } from "@/lib/api";

export default function ApprovalBlock({ block }: { block: ApprovalBlockT }) {
  const id = block.pending_action_id;
  const [status, setStatus] = useState<string>("loading");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!id) {
      setStatus("missing");
      return;
    }
    try {
      const rows = await listPendingActions();
      const found = rows.find((r) => r.id === id);
      setStatus(found ? found.status : "unknown");
    } catch {
      setStatus("unknown");
    }
  }, [id]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!id) {
    return <div className="text-2xs text-text-muted">Approval required for an action.</div>;
  }

  const act = async (fn: (x: string) => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn(id);
      await refresh();
    } catch {
      setStatus("unknown");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="px-3 py-2 rounded-[8px] border border-amber-500/30 bg-amber-500/5 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 min-w-0">
        {busy ? (
          <Loader2 size={13} className="text-dawn animate-spin flex-shrink-0" />
        ) : (
          <ShieldCheck size={13} className="text-amber-600 flex-shrink-0" />
        )}
        <span className="text-xs text-text-secondary truncate">
          {status === "approved" ? "Approved — action ran." :
           status === "rejected" ? "Rejected." :
           status === "completed" ? "Completed." :
           status === "pending" ? "Pending approval." :
           "Awaiting approval."}
        </span>
      </div>
      {status === "pending" && (
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => act(rejectPendingAction)}
            disabled={busy}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-2xs font-medium text-ember border border-ember/40 hover:bg-ember/5 disabled:opacity-40"
          >
            <ShieldX size={11} /> Reject
          </button>
          <button
            onClick={() => act(approvePendingAction)}
            disabled={busy}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-2xs font-medium text-white bg-dawn/90 hover:bg-dawn disabled:opacity-40"
          >
            <ShieldCheck size={11} /> Approve
          </button>
        </div>
      )}
    </div>
  );
}
