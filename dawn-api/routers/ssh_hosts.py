"""
SSH Host management endpoints.
CRUD for SSH host configurations and session logs.
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


class SSHHostCreate(BaseModel):
    label: str
    hostname: str
    port: int = 22
    username: str = "root"
    auth_method: str = "key"
    encrypted_key: Optional[str] = None
    encrypted_password: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None


class SSHHostUpdate(BaseModel):
    label: Optional[str] = None
    hostname: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    auth_method: Optional[str] = None
    encrypted_key: Optional[str] = None
    encrypted_password: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/ssh/hosts", tags=["ssh"])
async def list_ssh_hosts(_: None = Depends(verify_key)):
    """List all SSH hosts."""
    try:
        supabase = db.get_db()
        res = supabase.table("ssh_hosts").select(
            "id, label, hostname, port, username, auth_method, tags, notes, is_active, last_connected_at, created_at"
        ).order("label").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list SSH hosts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ssh/hosts", tags=["ssh"])
async def create_ssh_host(req: SSHHostCreate, _: None = Depends(verify_key)):
    """Add a new SSH host."""
    try:
        supabase = db.get_db()
        res = supabase.table("ssh_hosts").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create host")
        return res.data[0]
    except Exception as e:
        logger.error(f"Failed to create SSH host: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ssh/hosts/{host_id}", tags=["ssh"])
async def get_ssh_host(host_id: str, _: None = Depends(verify_key)):
    """Get a single SSH host."""
    try:
        supabase = db.get_db()
        res = supabase.table("ssh_hosts").select("*").eq("id", host_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Host not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/ssh/hosts/{host_id}", tags=["ssh"])
async def update_ssh_host(host_id: str, req: SSHHostUpdate, _: None = Depends(verify_key)):
    """Update an SSH host."""
    try:
        supabase = db.get_db()
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if data:
            supabase.table("ssh_hosts").update(data).eq("id", host_id).execute()
        res = supabase.table("ssh_hosts").select("*").eq("id", host_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Host not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/ssh/hosts/{host_id}", tags=["ssh"])
async def delete_ssh_host(host_id: str, _: None = Depends(verify_key)):
    """Delete an SSH host."""
    try:
        supabase = db.get_db()
        supabase.table("ssh_hosts").delete().eq("id", host_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ssh/logs", tags=["ssh"])
async def list_ssh_logs(limit: int = 50, host_id: Optional[str] = None, _: None = Depends(verify_key)):
    """List SSH session logs."""
    try:
        supabase = db.get_db()
        q = supabase.table("ssh_session_logs").select("*").order("created_at", desc=True).limit(limit)
        if host_id:
            q = q.eq("host_id", host_id)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list SSH logs: {e}")
        return []
