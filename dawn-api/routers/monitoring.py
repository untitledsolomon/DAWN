"""
Monitoring & Alerting endpoints — uptime checks, alert rules, alert events.
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


class MonitorTargetCreate(BaseModel):
    name: str
    target_type: str  # 'http', 'ping', 'port', 'process', 'custom'
    target_config: dict
    check_interval_seconds: int = 60
    timeout_seconds: int = 10


class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    condition_type: str  # 'threshold', 'pattern', 'absence', 'change'
    condition_config: dict
    severity: str = "warning"
    channel: list[str] = ["in_app"]
    cooldown_minutes: int = 60


@router.get("/monitor/targets", tags=["monitoring"])
async def list_monitor_targets(_: None = Depends(verify_key)):
    """List all monitoring targets."""
    try:
        supabase = db.get_db()
        res = supabase.table("monitor_targets").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list monitor targets: {e}")
        return []


@router.post("/monitor/targets", tags=["monitoring"])
async def create_monitor_target(req: MonitorTargetCreate, _: None = Depends(verify_key)):
    """Add a new monitoring target."""
    try:
        supabase = db.get_db()
        res = supabase.table("monitor_targets").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create target")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/monitor/targets/{target_id}", tags=["monitoring"])
async def delete_monitor_target(target_id: str, _: None = Depends(verify_key)):
    """Delete a monitoring target."""
    try:
        supabase = db.get_db()
        supabase.table("monitor_targets").delete().eq("id", target_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitor/checks", tags=["monitoring"])
async def list_monitor_checks(
    target_id: Optional[str] = None,
    limit: int = 100,
    _: None = Depends(verify_key),
):
    """List recent monitor checks."""
    try:
        supabase = db.get_db()
        q = supabase.table("monitor_checks").select("*").order("checked_at", desc=True).limit(limit)
        if target_id:
            q = q.eq("target_id", target_id)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list monitor checks: {e}")
        return []


@router.get("/monitor/status", tags=["monitoring"])
async def get_monitor_status(_: None = Depends(verify_key)):
    """Get overall monitoring status — count of up/down targets."""
    try:
        supabase = db.get_db()
        
        # Get latest check for each target
        targets_res = supabase.table("monitor_targets").select("id, name").eq("is_active", True).execute()
        targets = targets_res.data or []
        
        results = []
        for t in targets:
            check_res = supabase.table("monitor_checks").select(
                "status, response_time_ms, checked_at"
            ).eq("target_id", t["id"]).order("checked_at", desc=True).limit(1).execute()
            
            latest = check_res.data[0] if check_res.data else None
            results.append({
                **t,
                "latest_check": latest,
            })
        
        up_count = sum(1 for r in results if r.get("latest_check") and r["latest_check"]["status"] == "up")
        down_count = sum(1 for r in results if r.get("latest_check") and r["latest_check"]["status"] == "down")
        
        return {
            "targets": results,
            "summary": {
                "total": len(results),
                "up": up_count,
                "down": down_count,
                "healthy": up_count == len(results) if results else True,
            }
        }
    except Exception as e:
        logger.error(f"Failed to get monitor status: {e}")
        return {"targets": [], "summary": {"total": 0, "up": 0, "down": 0, "healthy": True}}


@router.get("/alerts/rules", tags=["monitoring"])
async def list_alert_rules(_: None = Depends(verify_key)):
    """List all alert rules."""
    try:
        supabase = db.get_db()
        res = supabase.table("alert_rules").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list alert rules: {e}")
        return []


@router.post("/alerts/rules", tags=["monitoring"])
async def create_alert_rule(req: AlertRuleCreate, _: None = Depends(verify_key)):
    """Create a new alert rule."""
    try:
        supabase = db.get_db()
        res = supabase.table("alert_rules").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create rule")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/alerts/rules/{rule_id}", tags=["monitoring"])
async def update_alert_rule(rule_id: str, req: AlertRuleCreate, _: None = Depends(verify_key)):
    """Update an alert rule."""
    try:
        supabase = db.get_db()
        supabase.table("alert_rules").update(req.model_dump()).eq("id", rule_id).execute()
        res = supabase.table("alert_rules").select("*").eq("id", rule_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Rule not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/rules/{rule_id}", tags=["monitoring"])
async def delete_alert_rule(rule_id: str, _: None = Depends(verify_key)):
    """Delete an alert rule."""
    try:
        supabase = db.get_db()
        supabase.table("alert_rules").delete().eq("id", rule_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts/events", tags=["monitoring"])
async def list_alert_events(
    severity: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    limit: int = 50,
    _: None = Depends(verify_key),
):
    """List alert events."""
    try:
        supabase = db.get_db()
        q = supabase.table("alert_events").select("*").order("created_at", desc=True).limit(limit)
        if severity:
            q = q.eq("severity", severity)
        if acknowledged is not None:
            q = q.eq("acknowledged", acknowledged)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list alert events: {e}")
        return []


@router.post("/alerts/events/{event_id}/acknowledge", tags=["monitoring"])
async def acknowledge_alert(event_id: str, _: None = Depends(verify_key)):
    """Acknowledge an alert event."""
    try:
        supabase = db.get_db()
        supabase.table("alert_events").update({
            "acknowledged": True,
            "acknowledged_at": "now()",
        }).eq("id", event_id).execute()
        return {"status": "acknowledged"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
