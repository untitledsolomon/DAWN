"""
MCP Server management endpoints.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator
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

    @field_validator("server_type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in ("stdio", "http"):
            raise ValueError("server_type must be 'stdio' or 'http'")
        return v


@router.get("/mcp/servers", tags=["mcp"])
async def list_mcp_servers(_: None = Depends(verify_key)):
    """List all MCP servers."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_servers").select(
            "id, name, description, server_type, enabled, tools_count, last_connected_at, created_at"
        ).order("name").execute())
        servers = res.data or []
        # Annotate each server with whether it has stored OAuth tokens, so the
        # UI can offer re-auth / revoke for OAuth-connected servers.
        if servers:
            ids = [s["id"] for s in servers]
            oauth_res = await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").select(
                "server_id"
            ).in_("server_id", ids).execute())
            oauth_ids = {r["server_id"] for r in (oauth_res.data or [])}
            for s in servers:
                s["has_oauth"] = s["id"] in oauth_ids
        return servers
    except Exception as e:
        logger.error(f"Failed to list MCP servers: {e}")
        return []


@router.post("/mcp/servers", tags=["mcp"])
async def create_mcp_server(req: MCPServerCreate, _: None = Depends(verify_key)):
    """Register a new MCP server."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_servers").insert(req.model_dump()).execute())
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create server")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/mcp/servers/{server_id}", tags=["mcp"])
async def update_mcp_server(server_id: str, req: MCPServerCreate, _: None = Depends(verify_key)):
    """Update an MCP server (e.g. edit a static API key without delete+recreate)."""
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("mcp_servers").update(req.model_dump()).eq("id", server_id).execute())
        res = await db._async_execute(lambda: supabase.table("mcp_servers").select("*").eq("id", server_id).execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Server not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/mcp/servers/{server_id}", tags=["mcp"])
async def delete_mcp_server(server_id: str, _: None = Depends(verify_key)):
    """Delete an MCP server."""
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("mcp_servers").delete().eq("id", server_id).execute())
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
        res = await db._async_execute(lambda: q.order("name").execute())
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list MCP tools: {e}")
        return []


@router.get("/tool-permissions", tags=["mcp"])
async def list_tool_permissions(_: None = Depends(verify_key)):
    """List all tool permissions."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("tool_permissions").select("*").order("tool_name").execute())
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list tool permissions: {e}")
        return []


@router.put("/tool-permissions/{permission_id}", tags=["mcp"])
async def update_tool_permission(permission_id: str, req: dict, _: None = Depends(verify_key)):
    """Update a tool permission."""
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("tool_permissions").update(req).eq("id", permission_id).execute())
        res = await db._async_execute(lambda: supabase.table("tool_permissions").select("*").eq("id", permission_id).execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Permission not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers/{server_id}/connect", tags=["mcp"])
async def connect_mcp_server(server_id: str, _: None = Depends(verify_key)):
    """Connect to an MCP server and discover its tools."""
    try:
        from tools.mcp_server import MCPTool
        tool = MCPTool()
        result = await tool._connect_server(server_id)
        if not result.success:
            # Surface whether the failure is because the server requires OAuth,
            # so the UI can offer a "Sign in" flow.
            requires_oauth = bool(result.metadata.get("requires_oauth"))
            raise HTTPException(status_code=400, detail=result.error,
                                 headers={"X-Requires-OAuth": "true"} if requires_oauth else None)
        return result.output
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mcp/servers/{server_id}/disconnect", tags=["mcp"])
async def disconnect_mcp_server(server_id: str, _: None = Depends(verify_key)):
    """Disconnect from an MCP server."""
    try:
        from tools.mcp_server import MCPTool
        tool = MCPTool()
        result = await tool._disconnect_server(server_id)
        return result.output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── OAuth 2.1 (MCP Authorization spec) ─────────────────────────────────────

@router.get("/mcp/servers/{server_id}/oauth/start", tags=["mcp"])
async def mcp_oauth_start(server_id: str, _: None = Depends(verify_key)):
    """Kick off discovery + DCR for an OAuth-protected MCP server.

    Returns the authorization_endpoint URL (with client_id, redirect_uri,
    code_challenge, state) for the frontend to open in a popup/redirect.
    """
    try:
        from tools import mcp_oauth
        if not mcp_oauth.oauth_enabled():
            raise HTTPException(status_code=500, detail="MCP OAuth support not available")
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_servers").select("url").eq("id", server_id).execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Server not found")
        url = (res.data[0] or {}).get("url")
        if not url:
            raise HTTPException(status_code=400, detail="Server has no URL")
        result = await mcp_oauth.start_oauth_flow(url)
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to start MCP OAuth flow: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mcp/oauth/callback", response_class=HTMLResponse)
async def mcp_oauth_callback(
    server_id: str = Query(...),
    code: str = Query(...),
    state: str = Query(...),
    iss: Optional[str] = Query(None),
):
    """Receive the OAuth authorization code, exchange it, and close the popup.

    This route is the registered redirect_uri. It exchanges the code at the
    token endpoint, persists the tokens, and returns a small page that
    postMessages back to the opener (the MCP servers page) so the frontend can
    retry connect automatically. No API key is required here — the AS redirects
    the browser to this URL.
    """
    try:
        from tools import mcp_oauth
        result = await mcp_oauth.handle_oauth_callback(server_id, code, state, iss=iss)
        return _callback_page(True, result.get("status", "success"))
    except Exception as e:
        logger.error(f"Failed to complete MCP OAuth callback: {e}")
        return _callback_page(False, str(e))


def _callback_page(success: bool, message: str) -> HTMLResponse:
    """Small HTML page that reports the OAuth result back to the opener popup."""
    status = "success" if success else "error"
    escaped = message.replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>DAWN — MCP OAuth</title></head>
<body style="font-family:system-ui,sans-serif;background:#0b0e14;color:#e6e6e6;display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
  <div style="text-align:center">
    <h2 style="margin:0 0 8px">{'Connected' if success else 'Sign-in failed'}</h2>
    <p style="color:#8b93a7;font-size:14px;margin:0">{'You can close this window.' if success else escaped}</p>
  </div>
  <script>
    try {{
      if (window.opener) {{
        window.opener.postMessage({{ type: 'mcp-oauth-result', status: '{status}', message: '{escaped}' }}, '*');
      }}
    }} catch (e) {{}}
    if (window.opener) {{ setTimeout(() => window.close(), 1500); }}
  </script>
</body>
</html>""")


@router.post("/mcp/servers/{server_id}/oauth/revoke", tags=["mcp"])
async def mcp_oauth_revoke(server_id: str, _: None = Depends(verify_key)):
    """Revoke a stored OAuth connection (remove tokens) without deleting the server."""
    try:
        from tools import mcp_oauth
        await mcp_oauth.delete_tokens(server_id)
        return {"status": "revoked"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
