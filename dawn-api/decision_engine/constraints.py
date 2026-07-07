"""Constraint evaluation primitives for decision workflows.

Supports two constraint types:
  - hard: Must pass. If any hard constraint fails, the option is eliminated.
  - soft: Weighted scoring. Higher weight = more important to the decision.

Each constraint is a callable that takes an option dict and returns a
ConstraintResult with pass/fail, score, and explanation.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ConstraintResult:
    name: str
    passed: bool
    score: Optional[float] = None  # 0.0 to 1.0, only for soft constraints
    weight: Optional[float] = None  # only for soft constraints
    explanation: str = ""


@dataclass
class Constraint:
    name: str
    constraint_type: str  # "hard" or "soft"
    weight: Optional[float] = None  # required for soft
    rule: Optional[str] = None
    evaluator: Optional[Callable[[dict], ConstraintResult]] = None

    def evaluate(self, option: dict) -> ConstraintResult:
        if self.evaluator:
            return self.evaluator(option)
        return ConstraintResult(
            name=self.name,
            passed=True,
            score=1.0 if self.constraint_type == "soft" else None,
            weight=self.weight,
            explanation=f"Constraint '{self.name}' passed (no custom evaluator)"
        )


def evaluate_constraints(
    option: dict,
    constraints: list[Constraint]
) -> tuple[bool, list[ConstraintResult]]:
    """Evaluate all constraints against an option.

    Returns (passed, results) where passed is False if any hard constraint failed.
    """
    results = []
    all_hard_passed = True

    for constraint in constraints:
        result = constraint.evaluate(option)
        results.append(result)

        if constraint.constraint_type == "hard" and not result.passed:
            all_hard_passed = False

    return all_hard_passed, results


def compute_soft_score(results: list[ConstraintResult]) -> float:
    """Compute weighted score from soft constraint results.

    Returns 0.0 if no soft constraints with weights exist.
    """
    total_weight = 0.0
    weighted_sum = 0.0

    for r in results:
        if r.weight is not None and r.score is not None:
            total_weight += r.weight
            weighted_sum += r.weight * r.score

    return weighted_sum / total_weight if total_weight > 0 else 0.0
