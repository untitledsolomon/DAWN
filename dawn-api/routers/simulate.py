"""What-if simulation engine.

Takes a snapshot of the current ontology state, applies hypothetical
mutations, and re-runs the workflow to show how the recommendation
changes.

Fix vs. the original implementation: the previous reroute_shipment.handler()
accepted a "_snapshot" input but only ever read "candidate_routes" — so a
mutated snapshot never actually changed anything, and baseline/scenario
were always identical. decision_engine/candidates.py now reads from
_snapshot when present, so mutations here actually flow through to the
ranking.

Key design decision unchanged from before: simulation reuses the same
constraint engine (decision_engine/constraint_interpreter.py + registry.py)
entirely. It's not a separate reasoning system — it runs the same
deterministic engine twice against different inputs and returns a diff.
"""
from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any, Optional


@dataclass
class Mutation:
    """A hypothetical change to apply to the ontology snapshot.

    Types:
      - vendor_reliability: Change a vendor's on_time_rate (or any property)
      - vendor_cost: Change a vendor's cost structure
      - route_unavailable: Mark a route as unavailable
      - contract_term: Change a contract term (e.g., penalty clause)
      - field_set: Generic — set any property on any snapshot collection item
                   by id. Prefer this for new object types instead of adding
                   another mutation_type branch.
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
    """Apply mutations to a deep-copied snapshot. Does not modify the original."""
    result = deepcopy(snapshot)
    for mutation in mutations:
        _apply_mutation(result, mutation)
    return result


_COLLECTION_BY_MUTATION_TYPE = {
    "vendor_reliability": "vendors",
    "vendor_cost": "vendors",
    "route_unavailable": "routes",
    "contract_term": "contracts",
}


def _apply_mutation(snapshot: dict, mutation: Mutation) -> None:
    if mutation.mutation_type == "field_set":
        # Generic path: caller specifies which collection via `property`
        # as "collection.field", e.g. property="routes.risk_score".
        if "." not in mutation.property:
            return
        collection_key, field_name = mutation.property.split(".", 1)
        for item in snapshot.get(collection_key, []):
            if item.get("id") == mutation.target_id:
                item[field_name] = mutation.new_value
        return

    collection_key = _COLLECTION_BY_MUTATION_TYPE.get(mutation.mutation_type)
    if not collection_key:
        return

    for item in snapshot.get(collection_key, []):
        if item.get("id") == mutation.target_id:
            if mutation.mutation_type == "route_unavailable":
                item["available"] = False
            else:
                item[mutation.property] = mutation.new_value


async def simulate_scenario(
    object_snapshot: dict,
    mutations: list[Mutation],
    workflow_name: str,
    workflow_inputs: dict,
    client_id: Optional[str] = None,
) -> SimulationResult:
    """Run a what-if simulation.

    1. Run the workflow on the current snapshot (baseline)
    2. Apply mutations to a copy
    3. Run the workflow on the mutated snapshot (scenario)
    4. Return both results plus a diff
    """
    from decision_engine.registry import run_workflow

    baseline = await run_workflow(
        workflow_name, {**workflow_inputs, "_snapshot": object_snapshot}, client_id=client_id
    )

    mutated = apply_mutations(object_snapshot, mutations)
    scenario = await run_workflow(
        workflow_name, {**workflow_inputs, "_snapshot": mutated}, client_id=client_id
    )

    diff = _compute_diff(baseline, scenario)

    return SimulationResult(baseline=baseline, scenario=scenario, diff=diff, mutations=mutations)


def _compute_diff(baseline: dict, scenario: dict) -> dict:
    baseline_rec = baseline.get("recommended") or {}
    scenario_rec = scenario.get("recommended") or {}

    return {
        "recommendation_changed": baseline_rec.get("option") != scenario_rec.get("option"),
        "baseline_recommendation": baseline_rec,
        "scenario_recommendation": scenario_rec,
        "baseline_ranked": baseline.get("ranked_options", []),
        "scenario_ranked": scenario.get("ranked_options", []),
    }
