"""What-if simulation engine.

Takes a snapshot of the current ontology state, applies hypothetical
mutations, and re-runs the decision workflow to show how the
recommendation changes.

Key design decision: Simulation reuses the Phase 2 constraint engine
entirely. It is not a separate reasoning system — it runs the same
deterministic engine twice against different inputs and returns a diff.
"""

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any, Optional


@dataclass
class Mutation:
    """A hypothetical change to apply to the ontology state.

    Types:
      - vendor_reliability: Change a vendor's on_time_rate
      - vendor_cost: Change a vendor's cost structure
      - route_unavailable: Mark a route as unavailable
      - contract_term: Change a contract term (e.g., penalty clause)
    """
    mutation_type: str
    target_id: str
    property: str
    new_value: Any
    label: str = ""


@dataclass
class SimulationResult:
    baseline: dict
    scenario: dict
    diff: dict
    mutations: list[Mutation]


def apply_mutations(snapshot: dict, mutations: list[Mutation]) -> dict:
    """Apply mutations to a deep-copied snapshot.

    Returns the mutated snapshot. Does not modify the original.
    """
    result = deepcopy(snapshot)

    for mutation in mutations:
        _apply_mutation(result, mutation)

    return result


def _apply_mutation(snapshot: dict, mutation: Mutation) -> None:
    """Apply a single mutation to the snapshot in-place."""
    if mutation.mutation_type == "vendor_reliability":
        for vendor in snapshot.get("vendors", []):
            if vendor.get("id") == mutation.target_id:
                vendor[mutation.property] = mutation.new_value

    elif mutation.mutation_type == "vendor_cost":
        for vendor in snapshot.get("vendors", []):
            if vendor.get("id") == mutation.target_id:
                vendor[mutation.property] = mutation.new_value

    elif mutation.mutation_type == "route_unavailable":
        for route in snapshot.get("routes", []):
            if route.get("id") == mutation.target_id:
                route["available"] = False

    elif mutation.mutation_type == "contract_term":
        for contract in snapshot.get("contracts", []):
            if contract.get("id") == mutation.target_id:
                contract[mutation.property] = mutation.new_value


def simulate_scenario(
    object_snapshot: dict,
    mutations: list[Mutation],
    workflow_name: str,
    workflow_inputs: dict
) -> SimulationResult:
    """Run a what-if simulation.

    1. Run the workflow on the current snapshot (baseline)
    2. Apply mutations to a copy
    3. Run the workflow on the mutated snapshot (scenario)
    4. Return both results plus a diff
    """
    from .registry import run_workflow

    baseline = run_workflow(workflow_name, {**workflow_inputs, "_snapshot": object_snapshot})

    mutated = apply_mutations(object_snapshot, mutations)
    scenario = run_workflow(workflow_name, {**workflow_inputs, "_snapshot": mutated})

    diff = _compute_diff(baseline, scenario)

    return SimulationResult(
        baseline=baseline,
        scenario=scenario,
        diff=diff,
        mutations=mutations
    )


def _compute_diff(baseline: dict, scenario: dict) -> dict:
    """Compute what changed between baseline and scenario."""
    baseline_rec = baseline.get("recommended", {})
    scenario_rec = scenario.get("recommended", {})

    return {
        "recommendation_changed": baseline_rec.get("option") != scenario_rec.get("option"),
        "baseline_recommendation": baseline_rec,
        "scenario_recommendation": scenario_rec,
        "baseline_ranked": baseline.get("ranked_options", []),
        "scenario_ranked": scenario.get("ranked_options", [])
    }
