"""
Audit Log endpoints — comprehensive action tracking.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


async def write_audit(
    action: str,
    actor_type: str,
    actor_ref: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    """Append an audit entry. audit_log has no DDL in the repo; migration 026
    creates it with id/action/actor_type/actor_ref/details/created_at. Failures
    are logged, never raised (auditing is best-effort)."""
    try:
        row: dict = {"action": action, "actor_type": actor_type}
        if actor_ref:
            row["actor_ref"] = actor_ref
        if details is not None:
            row["details"] = details
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("audit_log").insert(row).execute())
    except Exception as e:
        logger.warning(f"[audit] write failed for {action}: {e}")


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/audit/logs", tags=["audit"])
async def list_audit_logs(
    action: Optional[str] = None,
    actor_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(verify_key),
):
    """List audit log entries."""
    try:
        supabase = db.get_db()
        q = supabase.table("audit_log").select("*").order("created_at", desc=True).limit(limit).offset(offset)
        if action:
            q = q.eq("action", action)
        if actor_type:
            q = q.eq("actor_type", actor_type)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list audit logs: {e}")
        return []


@router.get("/audit/stats", tags=["audit"])
async def get_audit_stats(_: None = Depends(verify_key)):
    """Get audit log statistics."""
    try:
        supabase = db.get_db()
        
        # Count by action type
        actions_res = supabase.table("audit_log").select("action, count", count="exact").execute()
        
        # Recent activity (last 24h)
        recent_res = supabase.table("audit_log").select("id", count="exact").gte(
            "created_at", "now() - interval '24 hours'"
        ).execute()
        
        return {
            "total_entries": getattr(actions_res, 'count', 0) or 0,
            "recent_24h": getattr(recent_res, 'count', 0) or 0,
        }
    except Exception as e:
        logger.error(f"Failed to get audit stats: {e}")
        return {"total_entries": 0, "recent_24h": 0}
