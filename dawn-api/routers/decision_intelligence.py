"""Decision Intelligence API Router

Endpoints:
  POST /api/decision/run — Run a decision workflow
  POST /api/decision/{id}/approve — Approve/reject/override a decision
  GET  /api/decision/log — List decision history
  GET  /api/decision/log/{id} — Get full decision trace
  POST /api/decision/simulate — Run a what-if simulation
  POST /api/ontology/query — Query the ontology (any registered object type)
  GET  /api/ontology/objects — List registered ontology object types
  GET  /api/ontology/relationships — List registered ontology relationships
  POST /api/ontology/objects — Register a new object type (data-driven onboarding)
  POST /api/ontology/relationships — Register a new relationship
  GET  /api/admin/data-sources — Data source health status

This router is now a thin HTTP layer over two generic engines:
  - decision_engine/registry.py + constraint_interpreter.py + candidates.py
    for workflows (data-driven, not one Python file per workflow)
  - decision_engine/ontology_engine.py for object/relationship queries
    (driven by the ontology_objects / ontology_relationships tables,
    never a hardcoded table_map or per-relationship if/elif chain)

Adding a new client's domain model, or a new workflow, should never
require touching this file.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone
import json

from decision_engine.registry import run_workflow, list_workflows, check_approval_required
from decision_engine.simulate import Mutation, simulate_scenario
from decision_engine.ontology_engine import (
    query_object,
    list_object_types,
    list_relationships,
    register_object_type,
    register_relationship,
    OntologyError,
)
import db.client as db


router = APIRouter(prefix="/api", tags=["decision_intelligence"])


def _get_supabase():
    # Resolved per-call rather than at import time, matching the pattern
    # used elsewhere in dawn-api (see db/client.py's get_db()).
    return db.get_db()


# ─── Request/Response Models ───────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    workflow_name: str
    inputs: dict = {}
    triggered_by: str = "system"
    client_id: Optional[str] = None


class ApproveRequest(BaseModel):
    decision: str  # 'approved', 'rejected', 'overridden'
    by: str
    override_reason: Optional[str] = None


class SimulateRequest(BaseModel):
    workflow_name: str
    inputs: dict = {}
    mutations: list[dict] = []
    client_id: Optional[str] = None


class OntologyQueryRequest(BaseModel):
    object_type: str
    filters: dict = {}
    expand: list[str] = []
    limit: int = 20
    client_id: Optional[str] = None


class RegisterObjectTypeRequest(BaseModel):
    object_type: str
    source_table: str
    primary_key_column: str = "id"
    properties: dict = {}
    source_kind: str = "table"
    default_filter: dict = {}
    client_id: Optional[str] = None


class RegisterRelationshipRequest(BaseModel):
    from_object: str
    to_object: str
    relationship_name: str
    join_definition: dict
    client_id: Optional[str] = None


# ─── Decision Workflow Endpoints ───────────────────────────────────

@router.post("/decision/run")
async def run_decision_workflow(req: RunWorkflowRequest):
    """Run a decision workflow and log the result."""
    supabase = _get_supabase()
    try:
        result = await run_workflow(req.workflow_name, req.inputs, client_id=req.client_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    log_entry = {
        "workflow_name": req.workflow_name,
        "triggered_by": req.triggered_by,
        "input_snapshot": json.dumps(req.inputs),
        "constraint_results": json.dumps(
            [r.get("constraint_results", []) for r in result.get("ranked_options", [])]
        ),
        "ranked_options": json.dumps(result.get("ranked_options", [])),
        "recommended_option": json.dumps(result.get("recommended")),
        "llm_explanation": result.get("explanation", ""),
        "data_freshness": json.dumps({}),
        "executed": False,
    }

    try:
        log_resp = supabase.table("decision_log").insert(log_entry).execute()
        if log_resp.data:
            result["decision_log_id"] = log_resp.data[0]["id"]
    except Exception as e:
        # Logging failure shouldn't block the response
        result["decision_log_id"] = None
        result["_log_error"] = str(e)

    return result


@router.post("/decision/{decision_id}/approve")
async def approve_decision(decision_id: str, req: ApproveRequest):
    """Approve, reject, or override a decision."""
    supabase = _get_supabase()

    if req.decision not in ("approved", "rejected", "overridden"):
        raise HTTPException(status_code=400, detail="decision must be 'approved', 'rejected', or 'overridden'")

    if req.decision == "overridden" and not req.override_reason:
        raise HTTPException(status_code=400, detail="override_reason is required when overriding")

    update_data = {
        "human_decision": req.decision,
        "human_decision_by": req.by,
        "human_decision_at": datetime.now(timezone.utc).isoformat(),
        "executed": req.decision == "approved",
    }
    if req.override_reason:
        update_data["override_reason"] = req.override_reason

    try:
        resp = supabase.table("decision_log").update(update_data).eq("id", decision_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Decision log entry not found")
        return {"status": "ok", "decision": req.decision, "id": decision_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decision/log")
async def list_decision_log(
    workflow: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List decision history with optional filters."""
    supabase = _get_supabase()
    try:
        query = supabase.table("decision_log").select("*").order("created_at", desc=True)
        if workflow:
            query = query.eq("workflow_name", workflow)
        if decision:
            query = query.eq("human_decision", decision)
        resp = query.range(offset, offset + limit - 1).execute()
        return {"data": resp.data or [], "total": len(resp.data or [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decision/log/{decision_id}")
async def get_decision_trace(decision_id: str):
    """Get the full trace of a single decision."""
    supabase = _get_supabase()
    try:
        resp = supabase.table("decision_log").select("*").eq("id", decision_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Decision not found")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decision/workflows")
async def list_decision_workflows(client_id: Optional[str] = None):
    """List all registered workflows (data-driven — reads ontology_workflows)."""
    workflows = await list_workflows(client_id=client_id)
    return {
        "data": [
            {
                "name": wf.name,
                "description": wf.description,
                "requires_approval": wf.requires_approval,
                "candidate_object_type": wf.candidate_object_type,
                "input_schema": wf.input_schema,
                "client_id": wf.client_id,
            }
            for wf in workflows
        ]
    }


# ─── Simulation Endpoints ──────────────────────────────────────────

@router.post("/decision/simulate")
async def run_simulation(req: SimulateRequest):
    """Run a what-if simulation."""
    mutations = [
        Mutation(
            mutation_type=m.get("mutation_type", "unknown"),
            target_id=m.get("target_id", ""),
            property=m.get("property", ""),
            new_value=m.get("new_value"),
            label=m.get("label", ""),
        )
        for m in req.mutations
    ]

    snapshot = await _build_snapshot()

    try:
        result = await simulate_scenario(
            snapshot, mutations, req.workflow_name, req.inputs, client_id=req.client_id
        )
        return {
            "baseline": result.baseline,
            "scenario": result.scenario,
            "diff": result.diff,
            "mutations": [{"type": m.mutation_type, "target": m.target_id, "label": m.label} for m in mutations],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _build_snapshot() -> dict:
    """Build a generic ontology snapshot from every registered object type
    with backing collection data (vendors, routes, contracts, ...).

    Unlike the previous version, this doesn't hardcode which object
    types exist — it reads whatever is in ontology_objects and builds a
    snapshot keyed by a lowercase-plural convention (Vendor -> "vendors")
    so decision_engine/candidates.py's snapshot_key lookup keeps working
    for the seeded reroute_shipment example. New object types are picked
    up automatically without touching this function.
    """
    object_types = await list_object_types()
    snapshot: dict[str, list] = {}

    for obj in object_types:
        object_type = obj["object_type"]
        collection_key = object_type.lower() + "s"  # Vendor -> vendors, Route -> routes
        try:
            result = await query_object(object_type, limit=200)
            snapshot[collection_key] = result.get("data", [])
        except OntologyError:
            snapshot[collection_key] = []

    return snapshot


# ─── Ontology Endpoints ────────────────────────────────────────────

@router.post("/ontology/query")
async def query_ontology(req: OntologyQueryRequest):
    """Query the ontology for typed objects with expanded relationships.

    Works for ANY registered object type — driven entirely by
    ontology_objects / ontology_relationships. No object type name is
    hardcoded here; unknown object types return a 400, everything else
    is handled identically regardless of domain.
    """
    try:
        result = await query_object(
            req.object_type,
            filters=req.filters,
            expand=req.expand,
            limit=req.limit,
            client_id=req.client_id,
        )
        return {
            **result,
            "data_freshness": {
                "source": result["source_table"],
                "queried_at": datetime.now(timezone.utc).isoformat(),
            },
        }
    except OntologyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ontology/objects")
async def list_ontology_objects(client_id: Optional[str] = None):
    """List all registered ontology object types."""
    try:
        return {"data": await list_object_types(client_id=client_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ontology/objects")
async def create_ontology_object(req: RegisterObjectTypeRequest):
    """Register a new object type.

    This is the whole mechanism for onboarding a new client's domain
    model or extending an existing one — no code change required, only
    this call plus the backing table (or view) existing in the database.
    """
    try:
        row = await register_object_type(
            object_type=req.object_type,
            source_table=req.source_table,
            primary_key_column=req.primary_key_column,
            properties=req.properties,
            source_kind=req.source_kind,
            default_filter=req.default_filter,
            client_id=req.client_id,
        )
        return {"data": row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ontology/relationships")
async def list_ontology_relationships(client_id: Optional[str] = None):
    """List all registered ontology relationships."""
    try:
        return {"data": await list_relationships(client_id=client_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ontology/relationships")
async def create_ontology_relationship(req: RegisterRelationshipRequest):
    """Register a new relationship between two object types."""
    try:
        row = await register_relationship(
            from_object=req.from_object,
            to_object=req.to_object,
            relationship_name=req.relationship_name,
            join_definition=req.join_definition,
            client_id=req.client_id,
        )
        return {"data": row}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Admin Endpoints ───────────────────────────────────────────────

@router.get("/admin/data-sources")
async def data_source_health(client_id: Optional[str] = None):
    """Get health status of all data sources — driven by whatever object
    types are currently registered, not a hardcoded table list."""
    supabase = _get_supabase()
    sources = []

    object_types = await list_object_types(client_id=client_id)
    for obj in object_types:
        table = obj["source_table"]
        try:
            resp = supabase.table(table).select("count", count="exact").limit(0).execute()
            count = resp.count if hasattr(resp, "count") else 0
            sources.append({
                "name": obj["object_type"],
                "table": table,
                "status": "live" if count > 0 else "empty",
                "record_count": count,
                "last_sync": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            sources.append({
                "name": obj["object_type"],
                "table": table,
                "status": "error",
                "error": str(e),
                "record_count": 0,
            })

    return {"sources": sources}
