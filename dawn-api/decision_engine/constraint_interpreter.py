"""Generic constraint interpreter.

Replaces the previous pattern (decision_engine/workflows/reroute_shipment.py)
of one hand-written Python evaluator lambda per constraint per workflow.
Constraints are now data — a JSON spec per constraint, stored on
ontology_workflows.constraints — interpreted here by a small, fixed set
of rule types. Adding a new workflow, or a new constraint on an existing
workflow, is a data change: no new Python file, no new evaluator function.

Supported rule types (extend this list, not per-workflow files, when a
genuinely new comparison shape is needed):
  - field_truthy      : hard/soft — field on the option must be truthy
  - field_lte          : hard/soft — option[field] <= compare_to
  - field_gte          : hard/soft — option[field] >= compare_to
  - minimize_ratio      : soft — score = 1 - (option[field] / max_value)
  - maximize_field      : soft — score = option[field] directly (already 0-1)

compare_to / max_value can be a literal number, or
  {"input": "<workflow_input_key>", "multiplier": <float, optional>}
to reference a value from the workflow's inputs dict at evaluation time
(e.g. "15% of shipment_value", where shipment_value is a workflow input).
"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ConstraintResult:
    name: str
    passed: bool
    score: Optional[float] = None
    weight: Optional[float] = None
    explanation: str = ""


class ConstraintSpecError(Exception):
    """Raised when a constraint spec is malformed or references an unknown rule."""


def _resolve_value(value: Any, option: dict, inputs: dict) -> float:
    """Resolve a compare_to/max_value spec to a concrete number.

    Either a literal number, or {"input": key, "multiplier": m} pulling
    from the workflow's inputs dict (falls back to 0 if the input key is
    missing, so a malformed spec fails a comparison rather than crashing).
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and "input" in value:
        base = inputs.get(value["input"], 0) or 0
        multiplier = value.get("multiplier", 1)
        return float(base) * float(multiplier)
    return 0.0


def _format_explanation(spec: dict, field_value: Any, compare_value: Optional[float] = None) -> str:
    template = spec.get("explanation_template")
    if template:
        try:
            return template.format(field=field_value, compare_to=compare_value)
        except Exception:
            pass
    return f"{spec.get('field', spec.get('name'))}: {field_value}"


def evaluate_constraint(spec: dict, option: dict, inputs: dict) -> ConstraintResult:
    """Evaluate a single constraint spec against a single candidate option."""
    name = spec.get("name", "unnamed_constraint")
    ctype = spec.get("type", "soft")
    rule = spec.get("rule")
    field = spec.get("field")

    if rule == "field_truthy":
        value = bool(option.get(field))
        return ConstraintResult(
            name=name,
            passed=value,
            explanation=spec.get("explanation_true") if value else spec.get("explanation_false", f"{field} is falsy"),
        )

    if rule == "field_lte":
        field_value = option.get(field, 0) or 0
        compare_value = _resolve_value(spec.get("compare_to"), option, inputs)
        passed = float(field_value) <= compare_value
        return ConstraintResult(
            name=name,
            passed=passed,
            explanation=_format_explanation(spec, field_value, compare_value),
        )

    if rule == "field_gte":
        field_value = option.get(field, 0) or 0
        compare_value = _resolve_value(spec.get("compare_to"), option, inputs)
        passed = float(field_value) >= compare_value
        return ConstraintResult(
            name=name,
            passed=passed,
            explanation=_format_explanation(spec, field_value, compare_value),
        )

    if rule == "minimize_ratio":
        field_value = option.get(field, 0) or 0
        max_value = spec.get("max_value")
        if max_value is None and spec.get("max_value_field"):
            max_value = option.get(spec["max_value_field"], spec.get("max_value_default", 1))
        max_value = max_value or spec.get("max_value_default", 1)
        score = max(0.0, 1.0 - (float(field_value) / float(max_value))) if max_value else 0.0
        return ConstraintResult(
            name=name,
            passed=True,
            score=score,
            weight=spec.get("weight"),
            explanation=_format_explanation(spec, field_value) + f" (score: {score:.2f})",
        )

    if rule == "maximize_field":
        field_value = option.get(field, 0) or 0
        score = max(0.0, min(1.0, float(field_value)))
        return ConstraintResult(
            name=name,
            passed=True,
            score=score,
            weight=spec.get("weight"),
            explanation=_format_explanation(spec, field_value),
        )

    raise ConstraintSpecError(f"Unknown constraint rule type: {rule!r} (constraint '{name}')")


def evaluate_constraints(
    option: dict,
    constraint_specs: list[dict],
    inputs: dict,
) -> tuple[bool, list[ConstraintResult]]:
    """Evaluate every constraint spec against one option.

    Returns (hard_constraints_passed, results). A malformed constraint
    spec is treated as a failed hard constraint with a visible error
    explanation, rather than crashing the whole ranking — one bad
    constraint definition shouldn't take down every candidate.
    """
    results: list[ConstraintResult] = []
    all_hard_passed = True

    for spec in constraint_specs:
        try:
            result = evaluate_constraint(spec, option, inputs)
        except ConstraintSpecError as e:
            result = ConstraintResult(
                name=spec.get("name", "unnamed_constraint"),
                passed=False,
                explanation=f"Constraint spec error: {e}",
            )

        results.append(result)
        if spec.get("type", "soft") == "hard" and not result.passed:
            all_hard_passed = False

    return all_hard_passed, results


def compute_soft_score(results: list[ConstraintResult]) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for r in results:
        if r.weight is not None and r.score is not None:
            total_weight += r.weight
            weighted_sum += r.weight * r.score
    return weighted_sum / total_weight if total_weight > 0 else 0.0
