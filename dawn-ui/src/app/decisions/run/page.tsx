"use client";

import React, { useEffect, useState } from "react";
import { PlayCircle } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
import {
  listDecisionWorkflows,
  runDecisionWorkflow,
  approveDecision,
  type DecisionWorkflowSummary,
  type DecisionRunResult,
} from "@/lib/api";
import DecisionCard from "@/components/decision/DecisionCard";

const EXAMPLE_INPUTS: Record<string, string> = {
  reroute_shipment: JSON.stringify(
    {
      shipment_id: "example-shipment-1",
      reason: "Carrier delay reported",
      candidate_routes: [
        {
          id: "route-a",
          route_name: "Route A — Mombasa Corridor",
          carrier_name: "Carrier A",
          has_active_contract: true,
          projected_cost: 7500,
          shipment_value: 100000,
          transit_days: 4,
          on_time_rate: 0.93,
        },
        {
          id: "route-b",
          route_name: "Route B — Northern Corridor",
          carrier_name: "Carrier B",
          has_active_contract: true,
          projected_cost: 9200,
          shipment_value: 100000,
          transit_days: 3,
          on_time_rate: 0.88,
        },
      ],
    },
    null,
    2
  ),
};

export default function RunDecisionPage() {
  const [workflows, setWorkflows] = useState<DecisionWorkflowSummary[]>([]);
  const [workflowName, setWorkflowName] = useState("");
  const [inputsJson, setInputsJson] = useState("{}");
  const [inputsError, setInputsError] = useState<string | null>(null);
  const [result, setResult] = useState<DecisionRunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    listDecisionWorkflows()
      .then((wfs) => {
        setWorkflows(wfs);
        if (wfs.length > 0) {
          setWorkflowName(wfs[0].name);
          setInputsJson(EXAMPLE_INPUTS[wfs[0].name] || "{}");
        }
      })
      .catch((err) => setRunError(err.message || "Failed to load workflows"));
  }, []);

  const handleWorkflowChange = (name: string) => {
    setWorkflowName(name);
    setInputsJson(EXAMPLE_INPUTS[name] || "{}");
    setResult(null);
  };

  const handleRun = async () => {
    setRunError(null);
    setInputsError(null);
    setActionError(null);

    let inputs: Record<string, unknown>;
    try {
      inputs = JSON.parse(inputsJson);
    } catch {
      setInputsError("Inputs must be valid JSON.");
      return;
    }

    setLoading(true);
    try {
      const data = await runDecisionWorkflow({
        workflow_name: workflowName,
        inputs,
        triggered_by: "ui_user",
      });
      setResult(data);
    } catch (err: any) {
      setRunError(err.message || "Workflow run failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveDecision(id, { decision: "approved", by: "ui_user" });
    } catch (err: any) {
      setActionError(err.message || "Failed to approve");
    }
  };

  const handleReject = async (id: string) => {
    try {
      await approveDecision(id, { decision: "rejected", by: "ui_user" });
    } catch (err: any) {
      setActionError(err.message || "Failed to reject");
    }
  };

  const handleOverride = async (id: string, reason: string) => {
    try {
      await approveDecision(id, { decision: "overridden", by: "ui_user", override_reason: reason });
    } catch (err: any) {
      setActionError(err.message || "Failed to override");
    }
  };

  const selectedWorkflow = workflows.find((w) => w.name === workflowName);

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Run Decision</h1>
            <p className="text-text-muted text-2xs">
              Run a workflow live, review the recommendation, and approve, reject, or override it
            </p>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4 max-w-3xl space-y-4">
          <div className="bg-surface border border-rim rounded-xl p-4 space-y-3">
            <div>
              <label className="text-text-muted text-2xs font-medium block mb-1">Workflow</label>
              <select
                value={workflowName}
                onChange={(e) => handleWorkflowChange(e.target.value)}
                className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
              >
                {workflows.length === 0 && <option value="">No workflows registered</option>}
                {workflows.map((wf) => (
                  <option key={wf.name} value={wf.name}>
                    {wf.name}
                  </option>
                ))}
              </select>
              {selectedWorkflow?.description && (
                <p className="text-text-muted text-2xs mt-1">{selectedWorkflow.description}</p>
              )}
            </div>

            <div>
              <label className="text-text-muted text-2xs font-medium block mb-1">Inputs (JSON)</label>
              <textarea
                value={inputsJson}
                onChange={(e) => setInputsJson(e.target.value)}
                rows={12}
                className="w-full bg-elevated border border-rim rounded-lg px-3 py-2 text-text-primary text-2xs font-mono outline-none focus:border-dawn/50"
              />
              {inputsError && <p className="text-red-600 text-2xs mt-1">{inputsError}</p>}
              {selectedWorkflow?.input_schema && Object.keys(selectedWorkflow.input_schema).length > 0 && (
                <details className="mt-1">
                  <summary className="text-text-muted text-2xs cursor-pointer hover:text-text-primary transition-colors">
                    Expected input schema
                  </summary>
                  <pre className="text-2xs mt-1 text-text-secondary font-mono">
                    {JSON.stringify(selectedWorkflow.input_schema, null, 2)}
                  </pre>
                </details>
              )}
            </div>

            <button
              onClick={handleRun}
              disabled={loading || !workflowName}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30"
            >
              <PlayCircle size={14} />
              {loading ? "Running..." : "Run Workflow"}
            </button>
            {runError && <p className="text-red-600 text-2xs">{runError}</p>}
          </div>

          {actionError && <p className="text-red-600 text-2xs">{actionError}</p>}

          {result && (
            <DecisionCard
              workflow_name={result.workflow_name}
              ranked_options={result.ranked_options}
              recommended={result.recommended}
              explanation={result.explanation}
              requires_approval={result.requires_approval}
              decision_log_id={result.decision_log_id}
              onApprove={handleApprove}
              onReject={handleReject}
              onOverride={handleOverride}
            />
          )}
        </div>
      </div>
    </AppShell>
  );
}
