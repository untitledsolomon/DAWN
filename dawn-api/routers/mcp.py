"""
MCP Server management endpoints.
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


class MCPServerCreate(BaseModel):
    name: str
    description: Optional[str] = None
    server_type: str = "stdio"
    command: Optional[str] = None
    args: list[str] = []
    url: Optional[str] = None
    api_key: Optional[str] = None


@router.get("/mcp/servers", tags=["mcp"])
async def list_mcp_servers(_: None = Depends(verify_key)):
    """List all MCP servers."""
    try:
        supabase = db.get_db()
        res = supabase.table("mcp_servers").select(
            "id, name, description, server_type, enabled, tools_count, last_connected_at, created_at"
        ).order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list MCP servers: {e}")
        return []


@router.post("/mcp/servers", tags=["mcp"])
async def create_mcp_server(req: MCPServerCreate, _: None = Depends(verify_key)):
    """Register a new MCP server."""
    try:
        supabase = db.get_db()
        res = supabase.table("mcp_servers").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create server")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mcp/servers/{server_id}", tags=["mcp"])
async def delete_mcp_server(server_id: str, _: None = Depends(verify_key)):
    """Delete an MCP server."""
    try:
        supabase = db.get_db()
        supabase.table("mcp_servers").delete().eq("id", server_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/tools", tags=["mcp"])
async def list_mcp_tools(server_id: Optional[str] = None, _: None = Depends(verify_key)):
    """List all MCP tools."""
    try:
        supabase = db.get_db()
        q = supabase.table("mcp_tools").select("*, mcp_servers(name)").eq("enabled", True)
        if server_id:
            q = q.eq("server_id", server_id)
        res = q.order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        return []


@router.get("/tool-permissions", tags=["mcp"])
async def list_tool_permissions(_: None = Depends(verify_key)):
    """List all tool permissions."""
    try:
        supabase = db.get_db()
        res = supabase.table("tool_permissions").select("*").order("tool_name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list tool permissions: {e}")
        return []


@router.put("/tool-permissions/{permission_id}", tags=["mcp"])
async def update_tool_permission(permission_id: str, req: dict, _: None = Depends(verify_key)):
    """Update a tool permission."""
    try:
        supabase = db.get_db()
        supabase.table("tool_permissions").update(req).eq("id", permission_id).execute()
        res = supabase.table("tool_permissions").select("*").eq("id", permission_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Permission not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
