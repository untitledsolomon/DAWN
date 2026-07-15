"""
Regent Business Integrations — connect to CRM, PM, Axis, Forge, Sentinel, etc.
"""
import json
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


class IntegrationConfig(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    config: Optional[dict] = None


@router.get("/integrations", tags=["integrations"])
async def list_integrations(_: None = Depends(verify_key)):
    """List all Regent business integrations."""
    try:
        supabase = db.get_db()
        res = supabase.table("regent_integrations").select(
            "id, service_name, display_name, description, is_connected, last_sync_at, sync_status, config"
        ).order("service_name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list integrations: {e}")
        return []


@router.get("/integrations/{service_name}", tags=["integrations"])
async def get_integration(service_name: str, _: None = Depends(verify_key)):
    """Get a single integration."""
    try:
        supabase = db.get_db()
        res = supabase.table("regent_integrations").select("*").eq("service_name", service_name).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail=f"Integration '{service_name}' not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/integrations/{service_name}", tags=["integrations"])
async def update_integration(service_name: str, req: IntegrationConfig, _: None = Depends(verify_key)):
    """Configure an integration."""
    try:
        supabase = db.get_db()
        data = {}
        if req.base_url is not None:
            data["base_url"] = req.base_url
        if req.api_key is not None:
            data["api_key_encrypted"] = req.api_key  # TODO: encrypt at rest
        if req.config is not None:
            data["config"] = req.config
        
        if data:
            supabase.table("regent_integrations").update(data).eq("service_name", service_name).execute()
        
        res = supabase.table("regent_integrations").select("*").eq("service_name", service_name).execute()
        return res.data[0] if res.data else {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/integrations/{service_name}/sync", tags=["integrations"])
async def sync_integration(service_name: str, _: None = Depends(verify_key)):
    """Trigger a sync for an integration."""
    try:
        supabase = db.get_db()
        supabase.table("regent_integrations").update({
            "sync_status": "syncing",
            "last_sync_at": "now()",
        }).eq("service_name", service_name).execute()
        
        # TODO: Actual sync logic per integration type
        # For now, mark as complete
        supabase.table("regent_integrations").update({
            "sync_status": "idle",
            "is_connected": True,
        }).eq("service_name", service_name).execute()
        
        return {"status": "synced", "service": service_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/integrations/{service_name}/status", tags=["integrations"])
async def get_integration_status(service_name: str, _: None = Depends(verify_key)):
    """Get detailed status for an integration."""
    try:
        supabase = db.get_db()
        res = supabase.table("regent_integrations").select(
            "service_name, display_name, is_connected, last_sync_at, sync_status"
        ).eq("service_name", service_name).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Integration not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
