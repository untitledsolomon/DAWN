"""Generic candidate sourcing for data-driven workflows.

candidate_source (from ontology_workflows) describes how to get the
list of option dicts a workflow should rank. Two strategies today:

  {"strategy": "inputs_field", "field": "candidate_routes"}
      Candidates come directly from workflow_inputs[field] — used when
      the caller (agent, UI, or a simulation) already assembled the
      candidate list. This is what reroute_shipment uses.

  {"strategy": "ontology_query", "object": "Route",
   "filters_from_inputs": {"available": true}}
      Candidates come from a live ontology_query() call. filters_from_inputs
      maps ontology filter keys to either a literal value or
      {"input": "<workflow_input_key>"} to pull from workflow_inputs.

Simulation support: if workflow_inputs contains "_snapshot" (a dict of
lists, e.g. {"routes": [...], "vendors": [...]}), and the strategy is
"inputs_field", candidates are read from the snapshot's matching key
first. This is what makes what-if simulation actually change the
ranking — the previous hardcoded reroute_shipment.handler() accepted
_snapshot but never read it, so simulated mutations had no effect.
"""
from typing import Any


def _resolve_filter_value(value: Any, inputs: dict) -> Any:
    if isinstance(value, dict) and "input" in value:
        return inputs.get(value["input"])
    return value


async def get_candidates(candidate_source: dict, workflow_inputs: dict) -> list[dict]:
    strategy = candidate_source.get("strategy")

    if strategy == "inputs_field":
        field = candidate_source.get("field")
        snapshot = workflow_inputs.get("_snapshot")

        if snapshot is not None:
            # Simulation path: prefer the mutated snapshot's matching
            # collection over the raw workflow input, so mutations
            # applied by decision_engine/simulate.py actually take effect.
            snapshot_key = candidate_source.get("snapshot_key", field)
            if snapshot_key in snapshot:
                return snapshot.get(snapshot_key) or []

        return workflow_inputs.get(field, []) or []

    if strategy == "ontology_query":
        from decision_engine.ontology_engine import query_object

        object_type = candidate_source.get("object")
        filters_spec = candidate_source.get("filters_from_inputs", {})
        filters = {k: _resolve_filter_value(v, workflow_inputs) for k, v in filters_spec.items()}
        expand = candidate_source.get("expand", [])

        result = await query_object(
            object_type,
            filters=filters,
            expand=expand,
            limit=candidate_source.get("limit", 50),
            client_id=workflow_inputs.get("_client_id"),
        )
        return result.get("data", [])

    raise ValueError(f"Unknown candidate_source strategy: {strategy!r}")
