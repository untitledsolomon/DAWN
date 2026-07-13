"use client";

import React, { useEffect, useState } from "react";
import { FlaskConical, Plus, Trash2, AlertTriangle } from "lucide-react";
import AppShell from "@/components/layout/AppShell";
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

  // Base workflow inputs, as raw JSON text. reroute_shipment (and any
  // inputs_field-sourced workflow) has nothing to rank without candidates
  // being included here — they aren't pulled from the ontology automatically.
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
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-3 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-tight">Scenario Explorer</h1>
            <p className="text-text-muted text-2xs">Run what-if simulations against a decision workflow</p>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-6xl">
            {/* Configuration Panel */}
            <div className="space-y-4">
              <div className="bg-surface border border-rim rounded-xl p-4">
                <label className="text-text-muted text-2xs font-medium block mb-1">Workflow</label>
                <select
                  value={workflowName}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  className="w-full bg-surface border border-rim rounded-lg px-3 py-2 text-text-primary text-xs outline-none focus:border-dawn/50"
                >
                  {workflows.length === 0 && <option value="reroute_shipment">Reroute Shipment</option>}
                  {workflows.map((wf) => (
                    <option key={wf.name} value={wf.name}>
                      {wf.description || wf.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="bg-surface border border-rim rounded-xl p-4">
                <label className="text-text-muted text-2xs font-medium block mb-1">Base inputs (JSON)</label>
                <p className="text-text-muted text-2xs mb-2">
                  For input-sourced workflows like reroute_shipment, candidates must be included
                  here — the ontology isn&apos;t queried automatically.
                </p>
                <textarea
                  value={inputsJson}
                  onChange={(e) => setInputsJson(e.target.value)}
                  rows={10}
                  className="w-full bg-elevated border border-rim rounded-lg px-3 py-2 text-text-primary text-2xs font-mono outline-none focus:border-dawn/50"
                />
                {inputsError && <p className="text-red-600 text-2xs mt-1">{inputsError}</p>}
              </div>

              <div className="bg-surface border border-rim rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-text-primary text-xs font-semibold flex items-center gap-1.5">
                    <FlaskConical size={12} className="text-dawn" /> What If...
                  </h2>
                  <button
                    onClick={addMutation}
                    className="flex items-center gap-1 text-2xs px-2 py-1 text-dawn border border-dawn/30 rounded-lg hover:bg-dawn/10 transition-all"
                  >
                    <Plus size={10} /> Add Condition
                  </button>
                </div>

                {mutations.length === 0 && (
                  <p className="text-text-muted text-xs">
                    No conditions added yet. You can still run the baseline with zero mutations to
                    see the unmodified recommendation.
                  </p>
                )}

                {mutations.map((mutation, idx) => (
                  <div key={idx} className="mb-3 p-3 border border-rim rounded-lg bg-elevated/50">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-text-muted text-2xs font-medium">Condition {idx + 1}</span>
                      <button
                        onClick={() => removeMutation(idx)}
                        className="text-text-muted hover:text-red-600 transition-colors"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={mutation.mutation_type}
                        onChange={(e) => updateMutation(idx, "mutation_type", e.target.value)}
                        className="bg-surface border border-rim rounded-lg px-2 py-1.5 text-2xs text-text-primary outline-none focus:border-dawn/50"
                      >
                        {mutationTypeOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      <input
                        value={mutation.target_id}
                        onChange={(e) => updateMutation(idx, "target_id", e.target.value)}
                        placeholder="Target ID"
                        className="bg-surface border border-rim rounded-lg px-2 py-1.5 text-2xs font-mono text-text-primary outline-none focus:border-dawn/50"
                      />
                      <input
                        value={mutation.property}
                        onChange={(e) => updateMutation(idx, "property", e.target.value)}
                        placeholder="Property (e.g., on_time_rate)"
                        className="bg-surface border border-rim rounded-lg px-2 py-1.5 text-2xs font-mono text-text-primary outline-none focus:border-dawn/50"
                      />
                      <input
                        value={mutation.new_value}
                        onChange={(e) => updateMutation(idx, "new_value", e.target.value)}
                        placeholder="New value"
                        className="bg-surface border border-rim rounded-lg px-2 py-1.5 text-2xs font-mono text-text-primary outline-none focus:border-dawn/50"
                      />
                      <input
                        value={mutation.label}
                        onChange={(e) => updateMutation(idx, "label", e.target.value)}
                        placeholder="Label (optional)"
                        className="col-span-2 bg-surface border border-rim rounded-lg px-2 py-1.5 text-2xs text-text-primary outline-none focus:border-dawn/50"
                      />
                    </div>
                  </div>
                ))}

                <button
                  onClick={runSimulation}
                  disabled={loading}
                  className="w-full mt-1 flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all disabled:opacity-30"
                >
                  {loading ? "Running Simulation..." : "Run Simulation"}
                </button>
                {error && <p className="text-red-600 text-2xs mt-2">{error}</p>}
              </div>
            </div>

            {/* Results Panel */}
            <div>
              <h2 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-3">Result</h2>
              {!result && (
                <div className="bg-surface border border-rim rounded-xl p-8 text-center text-xs text-text-muted">
                  Configure conditions and run a simulation to see results here.
                </div>
              )}

              {result && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="bg-surface border border-rim rounded-xl p-3">
                      <h3 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">Baseline</h3>
                      {result.baseline?.recommended ? (
                        <div>
                          <p className="text-text-primary text-xs font-medium">
                            {result.baseline.recommended.option?.route_name || result.baseline.recommended.option?.id || "N/A"}
                          </p>
                          <p className="text-text-muted text-2xs mt-1">
                            Score: {result.baseline.recommended.score?.toFixed(2) ?? "N/A"}
                          </p>
                        </div>
                      ) : (
                        <p className="text-text-muted text-2xs">No recommendation</p>
                      )}
                    </div>
                    <div className="bg-surface border border-rim rounded-xl p-3">
                      <h3 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">Simulated</h3>
                      {result.scenario?.recommended ? (
                        <div>
                          <p className="text-text-primary text-xs font-medium">
                            {result.scenario.recommended.option?.route_name || result.scenario.recommended.option?.id || "N/A"}
                          </p>
                          <p className="text-text-muted text-2xs mt-1">
                            Score: {result.scenario.recommended.score?.toFixed(2) ?? "N/A"}
                          </p>
                        </div>
                      ) : (
                        <p className="text-text-muted text-2xs">No recommendation</p>
                      )}
                    </div>
                  </div>

                  {result.diff?.recommendation_changed ? (
                    <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-3 flex items-center gap-2">
                      <AlertTriangle size={14} className="text-amber-600 flex-shrink-0" />
                      <p className="text-amber-700 text-xs font-medium">
                        Recommendation changed under this scenario
                      </p>
                    </div>
                  ) : (
                    <div className="bg-elevated border border-rim rounded-xl p-3">
                      <p className="text-text-muted text-xs">No change in recommendation under this scenario.</p>
                    </div>
                  )}

                  <div className="bg-surface border border-rim rounded-xl p-3">
                    <h3 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">
                      Mutations Applied
                    </h3>
                    {result.mutations?.length ? (
                      result.mutations.map((m: any, idx: number) => (
                        <div key={idx} className="text-text-secondary text-2xs mb-1">
                          {m.label || `${m.type}: ${m.target}`}
                        </div>
                      ))
                    ) : (
                      <p className="text-text-muted text-2xs">No mutations applied — this was a baseline-only run.</p>
                    )}
                  </div>

                  <details>
                    <summary className="text-text-muted text-2xs font-medium cursor-pointer hover:text-text-primary transition-colors">
                      Full Simulation Data
                    </summary>
                    <pre className="mt-2 bg-elevated border border-rim rounded-lg p-3 text-2xs font-mono overflow-auto max-h-60 text-text-secondary">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
