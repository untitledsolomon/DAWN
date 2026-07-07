"""Decision Intelligence API Router

Endpoints:
  POST /api/decision/run — Run a decision workflow
  POST /api/decision/{id}/approve — Approve/reject/override a decision
  GET  /api/decision/log — List decision history
  GET  /api/decision/log/{id} — Get full decision trace
  POST /api/decision/simulate — Run a what-if simulation
  GET  /api/ontology/query — Query the ontology
  GET  /api/ontology/objects — List registered ontology objects
  GET  /api/ontology/relationships — List ontology relationships
  GET  /api/admin/data-sources — Data source health status
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime, timezone
import json

from ..decision_engine.registry import run_workflow, list_workflows, check_approval_required
from ..decision_engine.simulate import Mutation, simulate_scenario
from ..db.client import supabase

router = APIRouter(prefix="/api", tags=["decision_intelligence"])


# ─── Request/Response Models ───────────────────────────────────────

class RunWorkflowRequest(BaseModel):
    workflow_name: str
    inputs: dict = {}
    triggered_by: str = "system"


class ApproveRequest(BaseModel):
    decision: str  # 'approved', 'rejected', 'overridden'
    by: str
    override_reason: Optional[str] = None


class SimulateRequest(BaseModel):
    workflow_name: str
    inputs: dict = {}
    mutations: list[dict] = []


class OntologyQueryRequest(BaseModel):
    object_type: str
    filters: dict = {}
    expand: list[str] = []
    limit: int = 20


# ─── Decision Workflow Endpoints ───────────────────────────────────

@router.post("/decision/run")
async def run_decision_workflow(req: RunWorkflowRequest):
    """Run a decision workflow and log the result."""
    try:
        result = run_workflow(req.workflow_name, req.inputs)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Log to decision_log table
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
        "executed": False
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
    if req.decision not in ("approved", "rejected", "overridden"):
        raise HTTPException(status_code=400, detail="decision must be 'approved', 'rejected', or 'overridden'")

    if req.decision == "overridden" and not req.override_reason:
        raise HTTPException(status_code=400, detail="override_reason is required when overriding")

    update_data = {
        "human_decision": req.decision,
        "human_decision_by": req.by,
        "human_decision_at": datetime.now(timezone.utc).isoformat(),
        "executed": req.decision == "approved"
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
    offset: int = 0
):
    """List decision history with optional filters."""
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
    try:
        resp = supabase.table("decision_log").select("*").eq("id", decision_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Decision not found")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
            label=m.get("label", "")
        )
        for m in req.mutations
    ]

    # Build a snapshot from the current ontology state
    snapshot = _build_snapshot(req.inputs)

    try:
        result = simulate_scenario(snapshot, mutations, req.workflow_name, req.inputs)
        return {
            "baseline": result.baseline,
            "scenario": result.scenario,
            "diff": result.diff,
            "mutations": [{"type": m.mutation_type, "target": m.target_id, "label": m.label} for m in mutations]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _build_snapshot(inputs: dict) -> dict:
    """Build an ontology snapshot from current DB state."""
    snapshot = {"vendors": [], "routes": [], "contracts": [], "shipments": []}
    try:
        vendors = supabase.table("ontology_vendors").select("*").limit(100).execute()
        if vendors.data:
            snapshot["vendors"] = vendors.data
    except Exception:
        pass
    try:
        routes = supabase.table("ontology_routes").select("*").limit(100).execute()
        if routes.data:
            snapshot["routes"] = routes.data
    except Exception:
        pass
    try:
        contracts = supabase.table("ontology_contracts").select("*").limit(100).execute()
        if contracts.data:
            snapshot["contracts"] = contracts.data
    except Exception:
        pass
    return snapshot


# ─── Ontology Endpoints ────────────────────────────────────────────

@router.post("/ontology/query")
async def query_ontology(req: OntologyQueryRequest):
    """Query the ontology for typed objects with expanded relationships."""
    try:
        table_map = {
            "Shipment": "ontology_shipments",
            "Route": "ontology_routes",
            "Vendor": "ontology_vendors",
            "Contract": "ontology_contracts",
            "CostRecord": "ontology_cost_records",
            "DelayEvent": "ontology_delay_events",
            "CostCenter": "ontology_cost_centers",
        }

        table = table_map.get(req.object_type)
        if not table:
            raise HTTPException(status_code=400, detail=f"Unknown object type: {req.object_type}")

        query = supabase.table(table).select("*")

        for key, value in req.filters.items():
            query = query.eq(key, value)

        resp = query.limit(req.limit).execute()
        data = resp.data or []

        # Expand relationships if requested
        expansions = {}
        for rel in req.expand:
            parts = rel.split(".")
            expansions[parts[0]] = parts

        # Simple expansion: for each item, fetch related objects
        result = []
        for item in data:
            enriched = dict(item)
            for rel_name, rel_path in expansions.items():
                if rel_name == "current_route" and item.get("current_route_id"):
                    route = supabase.table("ontology_routes").select("*").eq("id", item["current_route_id"]).execute()
                    enriched["current_route"] = route.data[0] if route.data else None
                elif rel_name == "carrier" and item.get("carrier_vendor_id"):
                    vendor = supabase.table("ontology_vendors").select("*").eq("id", item["carrier_vendor_id"]).execute()
                    enriched["carrier"] = vendor.data[0] if vendor.data else None
                elif rel_name == "governing_contract" and item.get("governing_contract_id"):
                    contract = supabase.table("ontology_contracts").select("*").eq("id", item["governing_contract_id"]).execute()
                    enriched["governing_contract"] = contract.data[0] if contract.data else None
            result.append(enriched)

        return {
            "object": req.object_type,
            "data": result,
            "count": len(result),
            "data_freshness": {
                "source": table,
                "queried_at": datetime.now(timezone.utc).isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ontology/objects")
async def list_ontology_objects():
    """List all registered ontology object types."""
    try:
        resp = supabase.table("ontology_objects").select("*").execute()
        return {"data": resp.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ontology/relationships")
async def list_ontology_relationships():
    """List all registered ontology relationships."""
    try:
        resp = supabase.table("ontology_relationships").select("*").execute()
        return {"data": resp.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Admin Endpoints ───────────────────────────────────────────────

@router.get("/admin/data-sources")
async def data_source_health():
    """Get health status of all data sources."""
    sources = []
    tables = [
        ("ontology_shipments", "Shipment Tracking"),
        ("ontology_routes", "Route Data"),
        ("ontology_vendors", "Vendor Registry"),
        ("ontology_contracts", "Contract Management"),
        ("ontology_cost_records", "Cost Data"),
        ("ontology_delay_events", "Delay Tracking"),
        ("ontology_cost_centers", "Cost Centers"),
    ]

    for table, label in tables:
        try:
            resp = supabase.table(table).select("count", count="exact").limit(0).execute()
            count = resp.count if hasattr(resp, 'count') else 0
            sources.append({
                "name": label,
                "table": table,
                "status": "live" if count > 0 else "empty",
                "record_count": count,
                "last_sync": datetime.now(timezone.utc).isoformat()
            })
        except Exception as e:
            sources.append({
                "name": label,
                "table": table,
                "status": "error",
                "error": str(e),
                "record_count": 0
            })

    return {"sources": sources}
