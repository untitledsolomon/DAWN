"""Data-driven workflow registry.

Previously: every workflow required a hand-written Python module under
decision_engine/workflows/ with a handler() function, AND a call to
register_workflow() somewhere to put it in the in-memory registry —
the second half never actually happened for reroute_shipment, which is
why /api/decision/run raised "Unknown workflow" for it.

Now: workflows are rows in ontology_workflows (name, candidate_object_type,
candidate_source, constraints, input_schema). At startup (or on first
use), this module loads them from the DB into an in-memory cache. Adding
a workflow is an INSERT into ontology_workflows — never a new Python file,
never a manual register_workflow() call to remember.

Multi-tenancy: a workflow row with client_id set is only visible when
querying with that client_id (or no client_id filter at all, i.e. an
admin view). A NULL client_id workflow is shared/global and visible to
every client — this is the default for the seeded reroute_shipment
example today, since there's only one tenant in practice so far.
"""
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime, timezone
import logging

import db.client as db
from decision_engine.constraint_interpreter import evaluate_constraints, compute_soft_score
from decision_engine.candidates import get_candidates

logger = logging.getLogger(__name__)


@dataclass
class DecisionWorkflow:
    name: str
    description: str
    requires_approval: bool
    candidate_object_type: Optional[str]
    candidate_source: dict
    constraints: list = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)
    client_id: Optional[str] = None


# In-memory cache of workflows loaded from ontology_workflows. Not a
# hand-populated registry — refresh_workflows() is the only writer.
_cache: dict[str, DecisionWorkflow] = {}
_loaded = False


async def refresh_workflows() -> None:
    """(Re)load all workflows from ontology_workflows into the cache.
    Call this at startup and after any admin edit to the workflows table."""
    global _cache, _loaded
    supabase = db.get_db()
    resp = await db._async_execute(lambda: supabase.table("ontology_workflows").select("*").execute())
    rows = resp.data or []

    new_cache: dict[str, DecisionWorkflow] = {}
    for row in rows:
        new_cache[row["name"]] = DecisionWorkflow(
            name=row["name"],
            description=row.get("description", ""),
            requires_approval=row.get("requires_approval", True),
            candidate_object_type=row.get("candidate_object_type"),
            candidate_source=row.get("candidate_source", {}) or {},
            constraints=row.get("constraints", []) or [],
            input_schema=row.get("input_schema", {}) or {},
            client_id=row.get("client_id"),
        )

    _cache = new_cache
    _loaded = True
    logger.info(f"Loaded {len(_cache)} workflow(s) from ontology_workflows: {list(_cache.keys())}")


async def _ensure_loaded() -> None:
    if not _loaded:
        await refresh_workflows()


async def get_workflow(name: str, client_id: Optional[str] = None) -> Optional[DecisionWorkflow]:
    await _ensure_loaded()
    wf = _cache.get(name)
    if wf is None:
        return None
    # A client-scoped workflow is only visible to that client (or an
    # unscoped lookup, e.g. an admin view where client_id=None is passed
    # deliberately to mean "any"). A shared (client_id=None) workflow is
    # visible to everyone.
    if wf.client_id is not None and client_id is not None and wf.client_id != client_id:
        return None
    return wf


async def list_workflows(client_id: Optional[str] = None) -> list[DecisionWorkflow]:
    await _ensure_loaded()
    if client_id is None:
        return list(_cache.values())
    return [wf for wf in _cache.values() if wf.client_id in (None, client_id)]


async def run_workflow(name: str, inputs: dict, client_id: Optional[str] = None) -> dict:
    """Run a workflow by name with given inputs.

    Returns a structured result dict with ranked_options, recommended,
    requires_approval, explanation, timestamp — same shape callers
    (routers/decision_intelligence.py, tools/decision_workflow.py)
    already expect, so this is a drop-in replacement.
    """
    workflow = await get_workflow(name, client_id=client_id)
    if not workflow:
        raise ValueError(f"Unknown workflow: {name}")

    candidates = await get_candidates(workflow.candidate_source, inputs)

    if not candidates:
        return {
            "workflow_name": name,
            "ranked_options": [],
            "recommended": None,
            "requires_approval": workflow.requires_approval,
            "explanation": f"No candidate options available for workflow '{name}'.",
            "decision_log_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    ranked = _rank_candidates(candidates, workflow.constraints, inputs)

    if ranked and ranked[0]["hard_constraints_passed"]:
        rec = ranked[0]
        explanation = (
            f"Recommended option (score: {rec['soft_score']:.2f}): "
            + " | ".join(cr["explanation"] for cr in rec["constraint_results"] if cr.get("weight"))
        )
    else:
        explanation = "No viable options found — all candidates failed hard constraints."

    return {
        "workflow_name": name,
        "ranked_options": ranked,
        "recommended": {
            "option": ranked[0]["option"],
            "score": ranked[0]["soft_score"],
        } if ranked and ranked[0]["hard_constraints_passed"] else None,
        "requires_approval": workflow.requires_approval,
        "explanation": explanation,
        "decision_log_id": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _rank_candidates(candidates: list[dict], constraint_specs: list[dict], inputs: dict, top_n: int = 5) -> list[dict]:
    ranked = []
    for option in candidates:
        hard_passed, results = evaluate_constraints(option, constraint_specs, inputs)
        soft_score = compute_soft_score(results) if hard_passed else 0.0

        ranked.append({
            "option": option,
            "constraint_results": [
                {"name": r.name, "passed": r.passed, "score": r.score, "weight": r.weight, "explanation": r.explanation}
                for r in results
            ],
            "hard_constraints_passed": hard_passed,
            "soft_score": soft_score,
        })

    ranked.sort(key=lambda r: (r["hard_constraints_passed"], r["soft_score"]), reverse=True)
    return ranked[:top_n]


async def check_approval_required(workflow_name: str, client_id: Optional[str] = None) -> bool:
    workflow = await get_workflow(workflow_name, client_id=client_id)
    return workflow.requires_approval if workflow else True
