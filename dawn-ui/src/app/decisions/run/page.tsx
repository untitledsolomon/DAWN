"use client";

import React, { useEffect, useState } from "react";
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
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Run Decision</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
        Run a decision workflow live against the ontology, review the recommendation, and
        approve, reject, or override it. This logs an entry to the decision audit trail.
      </p>

      <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800 mb-6 space-y-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Workflow
          </label>
          <select
            value={workflowName}
            onChange={(e) => handleWorkflowChange(e.target.value)}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
          >
            {workflows.length === 0 && <option value="">No workflows registered</option>}
            {workflows.map((wf) => (
              <option key={wf.name} value={wf.name}>
                {wf.name}
              </option>
            ))}
          </select>
          {selectedWorkflow?.description && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{selectedWorkflow.description}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Inputs (JSON)
          </label>
          <textarea
            value={inputsJson}
            onChange={(e) => setInputsJson(e.target.value)}
            rows={12}
            className="w-full text-xs font-mono border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
          />
          {inputsError && <p className="text-xs text-red-600 dark:text-red-400 mt-1">{inputsError}</p>}
          {selectedWorkflow?.input_schema && Object.keys(selectedWorkflow.input_schema).length > 0 && (
            <details className="mt-1">
              <summary className="text-xs text-gray-500 dark:text-gray-400 cursor-pointer">
                Expected input schema
              </summary>
              <pre className="text-xs mt-1 text-gray-600 dark:text-gray-400">
                {JSON.stringify(selectedWorkflow.input_schema, null, 2)}
              </pre>
            </details>
          )}
        </div>

        <button
          onClick={handleRun}
          disabled={loading || !workflowName}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors disabled:opacity-50"
        >
          {loading ? "Running..." : "Run Workflow"}
        </button>
        {runError && <p className="text-sm text-red-600 dark:text-red-400">{runError}</p>}
      </div>

      {actionError && (
        <p className="text-sm text-red-600 dark:text-red-400 mb-3">{actionError}</p>
      )}

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
  );
}
