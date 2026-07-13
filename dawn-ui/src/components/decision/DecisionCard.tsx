"use client";

import React, { useState } from "react";
import { Star, Check, X, AlertTriangle } from "lucide-react";

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
  tradeoff_summary?: string;
}

interface DecisionCardProps {
  workflow_name: string;
  ranked_options: RankedOption[];
  recommended: { option: Record<string, any>; score: number; tradeoff_summary?: string } | null;
  explanation: string;
  requires_approval?: boolean;
  decision_log_id?: string | null;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onOverride?: (id: string, reason: string) => void;
}

// Derives a short human-readable summary from constraint results when the
// backend doesn't provide a precomputed tradeoff_summary string — the
// data-driven constraint engine returns per-constraint explanations
// instead of a single canned summary, so this stitches one together
// client-side from the weighted (soft) constraints.
function deriveTradeoffSummary(results: ConstraintResult[]): string {
  const weighted = results.filter((r) => r.weight != null && r.score != null);
  if (weighted.length === 0) return "";
  return weighted.map((r) => r.explanation).join(" · ");
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

  const recommendedSummary =
    recommended &&
    (recommended.tradeoff_summary ||
      deriveTradeoffSummary(
        ranked_options.find((o) => o.option === recommended.option)?.constraint_results || []
      ));

  return (
    <div className="bg-surface border border-rim rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-dawn/5 px-4 py-3 border-b border-rim">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-dawn text-2xs font-semibold uppercase tracking-wider">Decision</span>
            <h3 className="text-text-primary text-sm font-semibold mt-0.5">
              {workflow_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            </h3>
          </div>
          {decision_log_id && (
            <span className="text-text-muted text-2xs font-mono">#{decision_log_id.slice(0, 8)}</span>
          )}
        </div>
      </div>

      {/* Recommended Option */}
      {recommended && (
        <div className="px-4 py-3 border-b border-rim">
          <div className="flex items-center gap-1 mb-2">
            <Star size={12} className="text-ember fill-ember" />
            <span className="text-ember text-2xs font-semibold uppercase tracking-wider">Recommended</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
            <span className="text-text-primary font-medium">
              {recommended.option.route_name || recommended.option.name || "Option"}
            </span>
            {recommended.option.carrier_name && (
              <span className="text-text-secondary">Carrier: {recommended.option.carrier_name}</span>
            )}
            {recommended.option.transit_days && (
              <span className="text-text-secondary">Transit: {recommended.option.transit_days} days</span>
            )}
            {recommended.option.projected_cost && (
              <span className="text-text-secondary">Cost: {formatCurrency(recommended.option.projected_cost)}</span>
            )}
            {recommended.option.on_time_rate && (
              <span className="text-text-secondary">On-time: {formatPercent(recommended.option.on_time_rate)}</span>
            )}
          </div>
          <div className="mt-1 text-text-muted text-2xs">
            Score: {recommended.score.toFixed(2)}
            {recommendedSummary && <> — {recommendedSummary}</>}
          </div>
        </div>
      )}

      {/* Alternatives */}
      {ranked_options.length > 1 && (
        <div className="px-4 py-2 border-b border-rim">
          <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">Alternatives</span>
          {ranked_options.slice(1).map((opt, idx) => (
            <div
              key={idx}
              className={`mt-2 py-2 px-3 rounded-lg text-xs ${
                !opt.hard_constraints_passed ? "bg-red-500/5 opacity-60" : "bg-elevated/60"
              }`}
            >
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="text-text-primary font-medium">
                  {opt.option.route_name || opt.option.name || `Option ${idx + 2}`}
                </span>
                {opt.option.carrier_name && (
                  <span className="text-text-secondary">Carrier: {opt.option.carrier_name}</span>
                )}
                {opt.option.transit_days && (
                  <span className="text-text-secondary">Transit: {opt.option.transit_days} days</span>
                )}
                {opt.option.projected_cost && (
                  <span className="text-text-secondary">Cost: {formatCurrency(opt.option.projected_cost)}</span>
                )}
                {opt.option.on_time_rate && (
                  <span className="text-text-secondary">On-time: {formatPercent(opt.option.on_time_rate)}</span>
                )}
              </div>
              {/* Constraint pass/fail indicators */}
              <div className="mt-1 flex flex-wrap gap-1.5">
                {opt.constraint_results.map((cr, ci) => (
                  <span
                    key={ci}
                    className={`inline-flex items-center gap-0.5 text-2xs px-1.5 py-0.5 rounded font-mono ${
                      cr.passed
                        ? "text-dawn bg-dawn/10 border border-dawn/15"
                        : "text-red-700 bg-red-500/10 border border-red-500/15"
                    }`}
                  >
                    {cr.passed ? "✓" : "✗"} {cr.name.replace(/_/g, " ")}
                  </span>
                ))}
              </div>
              {!opt.hard_constraints_passed && (
                <div className="mt-1 text-red-600 text-2xs">Failed hard constraints — not eligible</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* LLM Explanation */}
      {explanation && (
        <div className="px-4 py-3 border-b border-rim">
          <span className="text-text-muted text-2xs font-semibold uppercase tracking-wider">DAWN&apos;s Take</span>
          <p className="mt-1 text-text-secondary text-xs leading-relaxed">{explanation}</p>
        </div>
      )}

      {/* Action Buttons */}
      {requires_approval && !actionTaken && (
        <div className="px-4 py-3 bg-elevated/50 flex flex-wrap gap-2">
          <button
            onClick={handleApprove}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-dawn/90 hover:bg-dawn text-white text-xs font-medium transition-all"
          >
            <Check size={12} /> Approve
          </button>
          <button
            onClick={() => setShowOverrideInput(!showOverrideInput)}
            className="px-4 py-1.5 rounded-lg bg-surface border border-rim text-text-secondary hover:bg-elevated text-xs font-medium transition-all"
          >
            Choose Alternative
          </button>
          <button
            onClick={handleReject}
            className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-surface border border-rim text-text-secondary hover:bg-elevated text-xs font-medium transition-all"
          >
            <X size={12} /> Reject
          </button>
        </div>
      )}

      {/* Override input */}
      {showOverrideInput && (
        <div className="px-4 py-3 bg-amber-500/5 border-t border-amber-500/20">
          <label className="text-text-secondary text-2xs font-medium block mb-1">
            Reason for override (required):
          </label>
          <textarea
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            className="w-full bg-surface border border-rim rounded-lg px-2 py-1.5 text-text-primary text-xs outline-none focus:border-dawn/50"
            rows={2}
            placeholder="Why are you choosing a different option?"
          />
          <button
            onClick={handleOverride}
            disabled={!overrideReason.trim()}
            className="mt-2 px-4 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium transition-all disabled:opacity-40"
          >
            Confirm Override
          </button>
        </div>
      )}

      {/* Action taken indicator */}
      {actionTaken && (
        <div className="px-4 py-2 text-center text-text-muted text-xs bg-elevated/50 flex items-center justify-center gap-1.5">
          {actionTaken === "approved" && (
            <>
              <Check size={12} className="text-dawn" /> Approved
            </>
          )}
          {actionTaken === "rejected" && (
            <>
              <X size={12} className="text-red-600" /> Rejected
            </>
          )}
          {actionTaken === "overridden" && (
            <>
              <AlertTriangle size={12} className="text-amber-600" /> Overridden
            </>
          )}
        </div>
      )}
    </div>
  );
}
