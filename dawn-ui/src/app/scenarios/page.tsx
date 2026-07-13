"use client";

import React, { useEffect, useState } from "react";
import {
  listDecisionWorkflows,
  runDecisionSimulation,
  type DecisionWorkflowSummary,
} from "@/lib/api";

interface Mutation {
  mutation_type: string;
  target_id: string;
  property: string;
  new_value: any;
  label: string;
}

export default function ScenariosPage() {
  const [workflows, setWorkflows] = useState<DecisionWorkflowSummary[]>([]);
  const [workflowName, setWorkflowName] = useState("reroute_shipment");
  const [mutations, setMutations] = useState<Mutation[]>([]);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Base workflow inputs, as raw JSON text. Fixed vs. the previous version,
  // which always sent inputs: {} — reroute_shipment (and any inputs_field-
  // sourced workflow) has nothing to rank without this, since candidates
  // come from workflow inputs, not automatically from the ontology.
  const [inputsJson, setInputsJson] = useState(
    JSON.stringify(
      {
        shipment_id: "example-shipment-1",
        reason: "Simulated delay",
        candidate_routes: [
          {
            id: "route-a",
            route_name: "Route A",
            has_active_contract: true,
            projected_cost: 8000,
            shipment_value: 100000,
            transit_days: 5,
            on_time_rate: 0.9,
            available: true,
          },
        ],
      },
      null,
      2
    )
  );
  const [inputsError, setInputsError] = useState<string | null>(null);

  useEffect(() => {
    listDecisionWorkflows()
      .then((wfs) => {
        setWorkflows(wfs);
        if (wfs.length > 0 && !wfs.some((w) => w.name === workflowName)) {
          setWorkflowName(wfs[0].name);
        }
      })
      .catch((err) => console.error("Failed to load workflows:", err));
  }, []);

  const addMutation = () => {
    setMutations([
      ...mutations,
      {
        mutation_type: "route_unavailable",
        target_id: "route-a",
        property: "available",
        new_value: false,
        label: "",
      },
    ]);
  };

  const updateMutation = (idx: number, field: string, value: any) => {
    const updated = [...mutations];
    (updated[idx] as any)[field] = value;
    setMutations(updated);
  };

  const removeMutation = (idx: number) => {
    setMutations(mutations.filter((_, i) => i !== idx));
  };

  const runSimulation = async () => {
    setError(null);
    setInputsError(null);

    let inputs: Record<string, unknown>;
    try {
      inputs = JSON.parse(inputsJson);
    } catch {
      setInputsError("Base inputs must be valid JSON.");
      return;
    }

    setLoading(true);
    try {
      const data = await runDecisionSimulation({
        workflow_name: workflowName,
        inputs,
        mutations: mutations.map((m) => ({
          mutation_type: m.mutation_type,
          target_id: m.target_id,
          property: m.property,
          new_value: m.new_value,
          label: m.label,
        })),
      });
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Simulation failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const mutationTypeOptions = [
    { value: "vendor_reliability", label: "Vendor Reliability Change" },
    { value: "vendor_cost", label: "Vendor Cost Change" },
    { value: "route_unavailable", label: "Route Unavailable" },
    { value: "contract_term", label: "Contract Term Change" },
    { value: "field_set", label: "Generic field set (collection.field)" },
  ];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">Scenario Explorer</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <div>
          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800 mb-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Workflow
            </label>
            <select
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-3 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            >
              {workflows.length === 0 && <option value="reroute_shipment">Reroute Shipment</option>}
              {workflows.map((wf) => (
                <option key={wf.name} value={wf.name}>
                  {wf.description || wf.name}
                </option>
              ))}
            </select>
          </div>

          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800 mb-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Base inputs (JSON)
            </label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              For workflows sourced from inputs (like reroute_shipment), candidates must be included
              here — the ontology isn&apos;t queried automatically.
            </p>
            <textarea
              value={inputsJson}
              onChange={(e) => setInputsJson(e.target.value)}
              rows={10}
              className="w-full text-xs font-mono border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            />
            {inputsError && <p className="text-xs text-red-600 dark:text-red-400 mt-1">{inputsError}</p>}
          </div>

          <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-gray-800">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white">What If...</h2>
              <button
                onClick={addMutation}
                className="text-xs px-2 py-1 text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-700 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20"
              >
                + Add Condition
              </button>
            </div>

            {mutations.length === 0 && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No conditions added yet. You can still run the baseline with zero mutations to see
                the unmodified recommendation.
              </p>
            )}

            {mutations.map((mutation, idx) => (
              <div
                key={idx}
                className="mb-3 p-3 border border-gray-200 dark:border-gray-700 rounded-md bg-gray-50 dark:bg-gray-900/50"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Condition {idx + 1}
                  </span>
                  <button
                    onClick={() => removeMutation(idx)}
                    className="text-xs text-red-500 hover:text-red-700"
                  >
                    Remove
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select
                    value={mutation.mutation_type}
                    onChange={(e) => updateMutation(idx, "mutation_type", e.target.value)}
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  >
                    {mutationTypeOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={mutation.target_id}
                    onChange={(e) => updateMutation(idx, "target_id", e.target.value)}
                    placeholder="Target ID (must match an id in base inputs)"
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                  <input
                    type="text"
                    value={mutation.property}
                    onChange={(e) => updateMutation(idx, "property", e.target.value)}
                    placeholder="Property (e.g., on_time_rate)"
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                  <input
                    type="text"
                    value={mutation.new_value}
                    onChange={(e) => updateMutation(idx, "new_value", e.target.value)}
                    placeholder="New value"
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                  />
                  <input
                    type="text"
                    value={mutation.label}
                    onChange={(e) => updateMutation(idx, "label", e.target.value)}
                    placeholder="Label (optional)"
                    className="text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-800 text-gray-900 dark:text-white col-span-2"
                  />
                </div>
              </div>
            ))}

            <button
              onClick={runSimulation}
              disabled={loading}
              className="w-full mt-3 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md transition-colors disabled:opacity-50"
            >
              {loading ? "Running Simulation..." : "Run Simulation"}
            </button>
            {error && <p className="text-sm text-red-600 dark:text-red-400 mt-2">{error}</p>}
          </div>
        </div>

        {/* Results Panel */}
        <div>
          <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Result</h2>
          {!result && (
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-8 bg-white dark:bg-gray-800 text-center text-sm text-gray-500 dark:text-gray-400">
              Configure conditions and run a simulation to see results here.
            </div>
          )}

          {result && (
            <div className="space-y-4">
              {/* Baseline vs Scenario comparison */}
              <div className="grid grid-cols-2 gap-3">
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
                  <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                    Baseline
                  </h3>
                  {result.baseline?.recommended ? (
                    <div className="text-sm">
                      <p className="font-medium text-gray-900 dark:text-white">
                        {result.baseline.recommended.option?.route_name || result.baseline.recommended.option?.id || "N/A"}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Score: {result.baseline.recommended.score?.toFixed(2) ?? "N/A"}
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500 dark:text-gray-400">No recommendation</p>
                  )}
                </div>
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
                  <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                    Simulated
                  </h3>
                  {result.scenario?.recommended ? (
                    <div className="text-sm">
                      <p className="font-medium text-gray-900 dark:text-white">
                        {result.scenario.recommended.option?.route_name || result.scenario.recommended.option?.id || "N/A"}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Score: {result.scenario.recommended.score?.toFixed(2) ?? "N/A"}
                      </p>
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500 dark:text-gray-400">No recommendation</p>
                  )}
                </div>
              </div>

              {/* Diff indicator */}
              {result.diff?.recommendation_changed ? (
                <div className="border border-yellow-200 dark:border-yellow-700 rounded-lg p-3 bg-yellow-50 dark:bg-yellow-900/10">
                  <p className="text-sm font-medium text-yellow-800 dark:text-yellow-300">
                    ⚠ Recommendation changed under this scenario
                  </p>
                </div>
              ) : (
                <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-900/30">
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    No change in recommendation under this scenario.
                  </p>
                </div>
              )}

              {/* Mutations applied */}
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-white dark:bg-gray-800">
                <h3 className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase mb-2">
                  Mutations Applied
                </h3>
                {result.mutations?.length ? (
                  result.mutations.map((m: any, idx: number) => (
                    <div key={idx} className="text-xs text-gray-700 dark:text-gray-300 mb-1">
                      {m.label || `${m.type}: ${m.target}`}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    No mutations applied — this was a baseline-only run.
                  </p>
                )}
              </div>

              {/* Full JSON */}
              <details>
                <summary className="text-xs font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-700 dark:hover:text-gray-300">
                  Full Simulation Data
                </summary>
                <pre className="mt-2 text-xs bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded p-2 overflow-auto max-h-60 text-gray-800 dark:text-gray-200">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
