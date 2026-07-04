"""
OSINT endpoints — manage targets, view scan results, schedule scans.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class OSINTTargetCreate(BaseModel):
    target_type: str  # 'domain', 'ip', 'email', 'username', 'organization'
    value: str
    label: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None


@router.get("/osint/targets", tags=["osint"])
async def list_osint_targets(_: None = Depends(verify_key)):
    """List all OSINT targets."""
    try:
        supabase = db.get_db()
        res = supabase.table("osint_targets").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list OSINT targets: {e}")
        return []


@router.post("/osint/targets", tags=["osint"])
async def create_osint_target(req: OSINTTargetCreate, _: None = Depends(verify_key)):
    """Add a new OSINT target."""
    try:
        supabase = db.get_db()
        res = supabase.table("osint_targets").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create target")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/osint/targets/{target_id}", tags=["osint"])
async def delete_osint_target(target_id: str, _: None = Depends(verify_key)):
    """Delete an OSINT target."""
    try:
        supabase = db.get_db()
        supabase.table("osint_targets").delete().eq("id", target_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/osint/results", tags=["osint"])
async def list_osint_results(
    target_id: Optional[str] = None,
    scan_type: Optional[str] = None,
    limit: int = 50,
    _: None = Depends(verify_key),
):
    """List OSINT scan results."""
    try:
        supabase = db.get_db()
        q = supabase.table("osint_scan_results").select("*").order("created_at", desc=True).limit(limit)
        if target_id:
            q = q.eq("target_id", target_id)
        if scan_type:
            q = q.eq("scan_type", scan_type)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list OSINT results: {e}")
        return []


@router.get("/osint/results/{result_id}", tags=["osint"])
async def get_osint_result(result_id: str, _: None = Depends(verify_key)):
    """Get a single OSINT scan result."""
    try:
        supabase = db.get_db()
        res = supabase.table("osint_scan_results").select("*").eq("id", result_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Result not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/osint/schedules", tags=["osint"])
async def list_osint_schedules(_: None = Depends(verify_key)):
    """List OSINT scan schedules."""
    try:
        supabase = db.get_db()
        res = supabase.table("osint_schedules").select("*, osint_targets(value, target_type)").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list OSINT schedules: {e}")
        return []
