"""
Settings and notification preferences endpoints.
Persists user configuration to the database.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Any
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ────────────────────────────────────────────────────────────

class SettingValue(BaseModel):
    value: Any


class NotificationPref(BaseModel):
    enabled: bool


class NotificationPrefsUpdate(BaseModel):
    agent_complete: Optional[bool] = None
    ingestion_finished: Optional[bool] = None
    graph_updates: Optional[bool] = None
    system_alerts: Optional[bool] = None


# ── Settings endpoints ────────────────────────────────────────────────

@router.get("/settings", tags=["settings"])
async def get_all_settings(_: None = Depends(verify_key)):
    """Get all settings as a key-value map. Handles JSONB value parsing."""
    try:
        supabase = db.get_db()
        res = supabase.table("settings").select("key, value").execute()
        result = {}
        for row in (res.data or []):
            key = row["key"]
            val = row["value"]
            # Supabase returns JSONB as the native Python type (str, int, bool, list, dict)
            # If it's a string that looks JSON-encoded, decode it
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    pass
            result[key] = val
        return result
    except Exception as e:
        logger.error(f"[settings] get_all_settings failed: {e}")
        # Return defaults so the frontend doesn't break
        return {
            "model": "deepseek",
            "local_endpoint": "http://localhost:11434",
            "theme": "light",
            "font_size": "m",
            "deepseek_api_key": "",
        }


@router.get("/settings/{key}", tags=["settings"])
async def get_setting(key: str, _: None = Depends(verify_key)):
    """Get a single setting by key."""
    try:
        supabase = db.get_db()
        res = supabase.table("settings").select("value").eq("key", key).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
        val = res.data[0]["value"]
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        return {"key": key, "value": val}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] get_setting failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get setting: {str(e)}")


@router.put("/settings/{key}", tags=["settings"])
async def update_setting(key: str, req: SettingValue, _: None = Depends(verify_key)):
    """Update or create a setting."""
    try:
        supabase = db.get_db()
        existing = supabase.table("settings").select("id").eq("key", key).execute()
        if existing.data:
            supabase.table("settings").update({
                "value": req.value,
                "updated_at": "now()",
            }).eq("key", key).execute()
        else:
            supabase.table("settings").insert({
                "key": key,
                "value": req.value,
            }).execute()
        return {"key": key, "value": req.value, "status": "saved"}
    except Exception as e:
        logger.error(f"[settings] update_setting failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update setting: {str(e)}")


# ── Notification preferences ──────────────────────────────────────────

@router.get("/notifications", tags=["notifications"])
async def get_notification_prefs(_: None = Depends(verify_key)):
    """Get all notification preferences."""
    try:
        supabase = db.get_db()
        res = supabase.table("notification_preferences").select("key, enabled").execute()
        result = {}
        for row in (res.data or []):
            result[row["key"]] = row["enabled"]
        return result
    except Exception as e:
        logger.error(f"[settings] get_notification_prefs failed: {e}")
        return {
            "agent_complete": True,
            "ingestion_finished": True,
            "graph_updates": False,
            "system_alerts": True,
        }


@router.put("/notifications", tags=["notifications"])
async def update_notification_prefs(
    req: NotificationPrefsUpdate,
    _: None = Depends(verify_key),
):
    """Update notification preferences."""
    try:
        supabase = db.get_db()
        updates = req.model_dump(exclude_none=True)
        for key, enabled in updates.items():
            existing = supabase.table("notification_preferences").select("id").eq("key", key).execute()
            if existing.data:
                supabase.table("notification_preferences").update({
                    "enabled": enabled,
                }).eq("key", key).execute()
            else:
                supabase.table("notification_preferences").insert({
                    "key": key,
                    "enabled": enabled,
                }).execute()
        return {"status": "saved", "updates": updates}
    except Exception as e:
        logger.error(f"[settings] update_notification_prefs failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update notification prefs: {str(e)}")


# ── Agent logs ────────────────────────────────────────────────────────

@router.get("/agent-logs", tags=["agent-logs"])
async def get_agent_logs(
    limit: int = 50,
    status_filter: Optional[str] = None,
    _: None = Depends(verify_key),
):
    """Get agent execution logs."""
    try:
        supabase = db.get_db()
        q = supabase.table("agent_logs").select("*").order("created_at", desc=True).limit(limit)
        if status_filter:
            q = q.eq("status", status_filter)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[settings] get_agent_logs failed: {e}")
        return []


@router.get("/agent-logs/{log_id}", tags=["agent-logs"])
async def get_agent_log(log_id: str, _: None = Depends(verify_key)):
    """Get a single agent log entry."""
    try:
        supabase = db.get_db()
        res = supabase.table("agent_logs").select("*").eq("id", log_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Log entry not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[settings] get_agent_log failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get agent log: {str(e)}")
