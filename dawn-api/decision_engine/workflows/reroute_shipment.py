"""Reroute Shipment decision workflow.

Given a shipment that needs rerouting (due to delay, cost, risk, or
vendor failure), this workflow:
  1. Identifies candidate routes + carriers
  2. Evaluates hard constraints (contract compliance, budget ceiling)
  3. Scores soft constraints (transit time, reliability, cost)
  4. Returns ranked options with tradeoff summaries
"""

from ..constraints import Constraint
from ..scoring import rank_options, build_workflow_result


def build_constraints() -> list[Constraint]:
    """Build the constraint set for reroute decisions."""
    return [
        Constraint(
            name="contract_compliance",
            constraint_type="hard",
            rule="candidate route's carrier must have active contract covering shipment cargo_type",
            evaluator=lambda opt: _check_contract_compliance(opt)
        ),
        Constraint(
            name="budget_ceiling",
            constraint_type="hard",
            rule="candidate route total cost <= shipment.value_usd * 0.15",
            evaluator=lambda opt: _check_budget_ceiling(opt)
        ),
        Constraint(
            name="transit_time",
            constraint_type="soft",
            weight=0.4,
            rule="minimize typical_transit_days",
            evaluator=lambda opt: _score_transit_time(opt)
        ),
        Constraint(
            name="reliability",
            constraint_type="soft",
            weight=0.4,
            rule="maximize carrier.on_time_rate",
            evaluator=lambda opt: _score_reliability(opt)
        ),
        Constraint(
            name="cost",
            constraint_type="soft",
            weight=0.2,
            rule="minimize projected_total_cost",
            evaluator=lambda opt: _score_cost(opt)
        ),
    ]


def _check_contract_compliance(option: dict) -> "ConstraintResult":
    from ..constraints import ConstraintResult
    has_contract = option.get("has_active_contract", False)
    return ConstraintResult(
        name="contract_compliance",
        passed=has_contract,
        explanation="Carrier has active contract" if has_contract else "No active contract for this cargo type"
    )


def _check_budget_ceiling(option: dict) -> "ConstraintResult":
    from ..constraints import ConstraintResult
    cost = option.get("projected_cost", 0)
    shipment_value = option.get("shipment_value", 1)
    ceiling = shipment_value * 0.15
    passed = cost <= ceiling
    return ConstraintResult(
        name="budget_ceiling",
        passed=passed,
        explanation=f"${cost:.0f} <= ${ceiling:.0f} (15% of ${shipment_value:.0f})" if passed
                    else f"${cost:.0f} exceeds ceiling of ${ceiling:.0f}"
    )


def _score_transit_time(option: dict) -> "ConstraintResult":
    from ..constraints import ConstraintResult
    days = option.get("transit_days", 30)
    # Lower is better: score = 1 - (days / max_expected_days)
    max_days = 30
    score = max(0.0, 1.0 - (days / max_days))
    return ConstraintResult(
        name="transit_time",
        passed=True,
        score=score,
        weight=0.4,
        explanation=f"{days} days transit (score: {score:.2f})"
    )


def _score_reliability(option: dict) -> "ConstraintResult":
    from ..constraints import ConstraintResult
    rate = option.get("on_time_rate", 0.5)
    return ConstraintResult(
        name="reliability",
        passed=True,
        score=rate,
        weight=0.4,
        explanation=f"On-time rate: {rate:.0%}"
    )


def _score_cost(option: dict) -> "ConstraintResult":
    from ..constraints import ConstraintResult
    cost = option.get("projected_cost", 0)
    max_cost = option.get("max_acceptable_cost", 100000)
    score = max(0.0, 1.0 - (cost / max_cost))
    return ConstraintResult(
        name="cost",
        passed=True,
        score=score,
        weight=0.2,
        explanation=f"${cost:.0f} (score: {score:.2f})"
    )


def handler(inputs: dict) -> dict:
    """Handle a reroute_shipment workflow invocation.

    Expected inputs:
      - shipment_id: str
      - reason: str (cost|delay|risk|vendor_failure)
      - candidate_routes: list[dict] (optional, from ontology_query)
      - _snapshot: dict (optional, for simulation)
    """
    shipment_id = inputs.get("shipment_id", "unknown")
    reason = inputs.get("reason", "unknown")
    candidates = inputs.get("candidate_routes", [])

    # If no candidates provided, return empty result
    if not candidates:
        return {
            "workflow_name": "reroute_shipment",
            "ranked_options": [],
            "recommended": None,
            "explanation": f"No candidate routes available for shipment {shipment_id}.",
            "input_summary": {
                "shipment_id": shipment_id,
                "reason": reason
            }
        }

    constraints = build_constraints()
    ranked = rank_options(candidates, constraints)

    # Build explanation
    if ranked and ranked[0].hard_constraints_passed:
        rec = ranked[0]
        explanation = (
            f"Recommended: {rec.option.get('route_name', 'Unknown')} via "
            f"{rec.option.get('carrier_name', 'Unknown')} — "
            f"{rec.option.get('transit_days', '?')} days, "
            f"${rec.option.get('projected_cost', 0):.0f}, "
            f"{rec.option.get('on_time_rate', 0):.0%} on-time. "
            f"Score: {rec.soft_score:.2f}"
        )
    else:
        explanation = "No viable options found — all candidates failed hard constraints."

    return {
        "workflow_name": "reroute_shipment",
        "ranked_options": [
            {
                "option": r.option,
                "constraint_results": [
                    {"name": cr.name, "passed": cr.passed, "score": cr.score,
                     "weight": cr.weight, "explanation": cr.explanation}
                    for cr in r.constraint_results
                ],
                "hard_constraints_passed": r.hard_constraints_passed,
                "soft_score": r.soft_score,
                "tradeoff_summary": r.tradeoff_summary
            }
            for r in ranked
        ],
        "recommended": {
            "option": ranked[0].option,
            "score": ranked[0].soft_score,
            "tradeoff_summary": ranked[0].tradeoff_summary
        } if ranked and ranked[0].hard_constraints_passed else None,
        "explanation": explanation,
        "input_summary": {
            "shipment_id": shipment_id,
            "reason": reason
        }
    }
