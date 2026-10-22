"""Shared expression-vector tests — both the Python evaluator (here) and the
TypeScript evaluator (dawn-ui vitest) must pass the same cases."""
import json
from pathlib import Path

import pytest

from ui.expr import evaluate, ExprError

FIXTURES = Path(__file__).parent / "fixtures" / "expr_cases.json"
CASES = json.loads(FIXTURES.read_text())


@pytest.mark.parametrize("case", CASES, ids=[c["expr"] for c in CASES])
def test_expr_case(case):
    expr = case["expr"]
    vars_ = {k: float(v) for k, v in case.get("vars", {}).items()}
    if case.get("error"):
        with pytest.raises(ExprError):
            evaluate(expr, vars_)
        return
    result = evaluate(expr, vars_)
    expected = case["expected"]
    tol = case.get("tol", 1e-9)
    assert abs(result - expected) <= tol, f"{expr} -> {result}, expected {expected}"
