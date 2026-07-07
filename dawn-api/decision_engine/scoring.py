"""Weighted scoring and ranking for decision workflow options."""

from dataclasses import dataclass, field
from typing import Any, Optional

from .constraints import ConstraintResult, compute_soft_score


@dataclass
class RankedOption:
    option: dict
    constraint_results: list[ConstraintResult]
    hard_constraints_passed: bool
    soft_score: float = 0.0
    tradeoff_summary: str = ""


@dataclass
class WorkflowResult:
    workflow_name: str
    ranked_options: list[RankedOption]
    recommended: Optional[RankedOption] = None
    explanation: str = ""


def rank_options(
    options: list[dict],
    constraints: list,
    top_n: int = 5
) -> list[RankedOption]:
    """Evaluate and rank options by constraint satisfaction.

    Steps:
    1. Evaluate all constraints for each option
    2. Filter out options failing hard constraints
    3. Score remaining options on soft constraints
    4. Sort by score descending
    """
    from .constraints import evaluate_constraints

    ranked = []

    for option in options:
        hard_passed, results = evaluate_constraints(option, constraints)
        soft_score = compute_soft_score(results) if hard_passed else 0.0

        # Build tradeoff summary
        tradeoff_parts = []
        for r in results:
            if r.weight and r.score is not None:
                tradeoff_parts.append(f"{r.name}: {r.score:.2f} (w={r.weight})")
            elif not r.passed:
                tradeoff_parts.append(f"{r.name}: FAILED")

        ranked.append(RankedOption(
            option=option,
            constraint_results=results,
            hard_constraints_passed=hard_passed,
            soft_score=soft_score,
            tradeoff_summary=" | ".join(tradeoff_parts)
        ))

    # Sort: hard-passing options first, then by soft score descending
    ranked.sort(key=lambda r: (r.hard_constraints_passed, r.soft_score), reverse=True)

    return ranked[:top_n]


def build_workflow_result(
    workflow_name: str,
    ranked: list[RankedOption],
    llm_explanation: str = ""
) -> WorkflowResult:
    """Build a structured workflow result with recommendation."""
    recommended = ranked[0] if ranked else None
    return WorkflowResult(
        workflow_name=workflow_name,
        ranked_options=ranked,
        recommended=recommended,
        explanation=llm_explanation
    )
