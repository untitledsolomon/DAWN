"use client";

import React, { useState } from "react";

interface ConstraintResult {
  name: string;
  passed: boolean;
  score?: number | null;
  weight?: number | null;
  explanation: string;
}

interface RankedOption {
  option: Record<string, any>;
  constraint_results: ConstraintResult[];
  hard_constraints_passed: boolean;
  soft_score: number;
  tradeoff_summary: string;
}

interface DecisionCardProps {
  workflow_name: string;
  ranked_options: RankedOption[];
  recommended: { option: Record<string, any>; score: number; tradeoff_summary: string } | null;
  explanation: string;
  requires_approval?: boolean;
  decision_log_id?: string | null;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onOverride?: (id: string, reason: string) => void;
}

export default function DecisionCard({
  workflow_name,
  ranked_options,
  recommended,
  explanation,
  requires_approval = true,
  decision_log_id,
  onApprove,
  onReject,
  onOverride,
}: DecisionCardProps) {
  const [showOverrideInput, setShowOverrideInput] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [actionTaken, setActionTaken] = useState<string | null>(null);

  const handleApprove = () => {
    if (decision_log_id && onApprove) {
      onApprove(decision_log_id);
      setActionTaken("approved");
    }
  };

  const handleReject = () => {
    if (decision_log_id && onReject) {
      onReject(decision_log_id);
      setActionTaken("rejected");
    }
  };

  const handleOverride = () => {
    if (decision_log_id && onOverride && overrideReason.trim()) {
      onOverride(decision_log_id, overrideReason);
      setActionTaken("overridden");
      setShowOverrideInput(false);
    }
  };

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);

  const formatPercent = (val: number) => `${(val * 100).toFixed(0)}%`;

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden shadow-sm">
      {/* Header */}
      <div className="bg-blue-50 dark:bg-blue-900/20 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-xs font-semibold text-blue-600 dark:text-blue-400 uppercase tracking-wide">
              Decision
            </span>
            <h3 className="text-sm font-bold text-gray-900 dark:text-white mt-0.5">
              {workflow_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </h3>
          </div>
          {decision_log_id && (
            <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">
              #{decision_log_id.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      {/* Recommended Option */}
      {recommended && (
        <div className="px-4 py-3 bg-green-50 dark:bg-green-900/10 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-1 mb-2">
            <span className="text-yellow-500 text-sm">⭐</span>
            <span className="text-xs font-semibold text-green-700 dark:text-green-400 uppercase">
              Recommended
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <span className="font-medium text-gray-900 dark:text-white">
              {recommended.option.route_name || recommended.option.name || "Option"}
            </span>
            {recommended.option.carrier_name && (
              <span className="text-gray-600 dark:text-gray-400">
                Carrier: {recommended.option.carrier_name}
              </span>
            )}
            {recommended.option.transit_days && (
              <span className="text-gray-600 dark:text-gray-400">
                Transit: {recommended.option.transit_days} days
              </span>
            )}
            {recommended.option.projected_cost && (
              <span className="text-gray-600 dark:text-gray-400">
                Cost: {formatCurrency(recommended.option.projected_cost)}
              </span>
            )}
            {recommended.option.on_time_rate && (
              <span className="text-gray-600 dark:text-gray-400">
                On-time: {formatPercent(recommended.option.on_time_rate)}
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Score: {recommended.score.toFixed(2)} — {recommended.tradeoff_summary}
          </div>
        </div>
      )}

      {/* Alternatives */}
      {ranked_options.length > 1 && (
        <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700">
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
            Alternatives
          </span>
          {ranked_options.slice(1).map((opt, idx) => (
            <div
              key={idx}
              className={`mt-2 py-2 px-3 rounded text-sm ${
                !opt.hard_constraints_passed
                  ? "bg-red-50 dark:bg-red-900/10 opacity-60"
                  : "bg-gray-50 dark:bg-gray-800/50"
              }`}
            >
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="font-medium text-gray-900 dark:text-white">
                  {opt.option.route_name || opt.option.name || `Option ${idx + 2}`}
                </span>
                {opt.option.carrier_name && (
                  <span className="text-gray-600 dark:text-gray-400">
                    Carrier: {opt.option.carrier_name}
                  </span>
                )}
                {opt.option.transit_days && (
                  <span className="text-gray-600 dark:text-gray-400">
                    Transit: {opt.option.transit_days} days
                  </span>
                )}
                {opt.option.projected_cost && (
                  <span className="text-gray-600 dark:text-gray-400">
                    Cost: {formatCurrency(opt.option.projected_cost)}
                  </span>
                )}
                {opt.option.on_time_rate && (
                  <span className="text-gray-600 dark:text-gray-400">
                    On-time: {formatPercent(opt.option.on_time_rate)}
                  </span>
                )}
              </div>
              {/* Constraint pass/fail indicators */}
              <div className="mt-1 flex flex-wrap gap-2">
                {opt.constraint_results.map((cr, ci) => (
                  <span
                    key={ci}
                    className={`inline-flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded ${
                      cr.passed
                        ? "text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-900/20"
                        : "text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/20"
                    }`}
                  >
                    {cr.passed ? "✓" : "✗"} {cr.name.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
              {!opt.hard_constraints_passed && (
                <div className="mt-1 text-xs text-red-600 dark:text-red-400">
                  Failed hard constraints — not eligible
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* LLM Explanation */}
      {explanation && (
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <span className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">
            DAWN&apos;s Take
          </span>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{explanation}</p>
        </div>
      )}

      {/* Action Buttons */}
      {requires_approval && !actionTaken && (
        <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800/50 flex flex-wrap gap-2">
          <button
            onClick={handleApprove}
            className="px-4 py-1.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md transition-colors"
          >
            Approve
          </button>
          <button
            onClick={() => setShowOverrideInput(!showOverrideInput)}
            className="px-4 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors"
          >
            Choose Alternative
          </button>
          <button
            onClick={handleReject}
            className="px-4 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors"
          >
            Reject
          </button>
        </div>
      )}

      {/* Override input */}
      {showOverrideInput && (
        <div className="px-4 py-3 bg-yellow-50 dark:bg-yellow-900/10 border-t border-gray-200 dark:border-gray-700">
          <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
            Reason for override (required):
          </label>
          <textarea
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            className="w-full text-sm border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1.5 bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
            rows={2}
            placeholder="Why are you choosing a different option?"
          />
          <button
            onClick={handleOverride}
            disabled={!overrideReason.trim()}
            className="mt-2 px-4 py-1.5 text-sm font-medium text-white bg-yellow-600 hover:bg-yellow-700 rounded-md transition-colors disabled:opacity-50"
          >
            Confirm Override
          </button>
        </div>
      )}

      {/* Action taken indicator */}
      {actionTaken && (
        <div className="px-4 py-2 text-sm text-center text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50">
          {actionTaken === "approved" && "✓ Approved"}
          {actionTaken === "rejected" && "✗ Rejected"}
          {actionTaken === "overridden" && "⚠ Overridden"}
        </div>
      )}
    </div>
  );
}
