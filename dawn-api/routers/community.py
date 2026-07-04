"""
v27.0 — Community & Ecosystem
Open source release, plugin marketplace, documentation site, community forum
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class PluginCreate(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    author: str
    repository_url: Optional[str] = None
    entry_point: str
    dependencies: list[str] = []
    permissions: list[str] = []
    config_schema: Optional[dict] = None

class PluginUpdate(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[dict] = None

# ─── Plugin Marketplace ───────────────────────────────────────────────────

@router.get("/community/plugins", tags=["community"])
async def list_plugins(
    category: Optional[str] = None,
    installed_only: bool = False,
    _: None = Depends(verify_key),
):
    """List available and installed plugins."""
    try:
        supabase = db.get_db()
        
        if installed_only:
            res = supabase.table("plugins").select("*").eq("is_installed", True).order("name").execute()
        else:
            res = supabase.table("plugins").select("*").order("name").execute()
        
        return res.data or []
    except Exception as e:
        logger.error(f"[community] list plugins failed: {e}")
        return []


@router.post("/community/plugins", tags=["community"])
async def register_plugin(req: PluginCreate, _: None = Depends(verify_key)):
    """Register a new plugin."""
    try:
        supabase = db.get_db()
        res = supabase.table("plugins").insert({
            **req.model_dump(),
            "is_installed": False,
            "is_official": False,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[community] register plugin failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register plugin: {str(e)}")


@router.post("/community/plugins/{plugin_id}/install", tags=["community"])
async def install_plugin(plugin_id: str, _: None = Depends(verify_key)):
    """Install a plugin."""
    try:
        supabase = db.get_db()
        
        plugin = supabase.table("plugins").select("*").eq("id", plugin_id).execute()
        if not plugin.data:
            raise HTTPException(status_code=404, detail="Plugin not found")
        
        # Install dependencies
        deps = plugin.data[0].get("dependencies", [])
        if deps:
            try:
                import subprocess
                for dep in deps:
                    subprocess.run(["pip", "install", dep], check=True, capture_output=True)
            except Exception as e:
                logger.warning(f"[community] Failed to install dependency: {e}")
        
        supabase.table("plugins").update({
            "is_installed": True,
            "installed_at": "now()",
        }).eq("id", plugin_id).execute()
        
        return {"status": "installed", "plugin": plugin.data[0]["name"]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[community] install plugin failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to install plugin: {str(e)}")


@router.post("/community/plugins/{plugin_id}/uninstall", tags=["community"])
async def uninstall_plugin(plugin_id: str, _: None = Depends(verify_key)):
    """Uninstall a plugin."""
    try:
        supabase = db.get_db()
        supabase.table("plugins").update({
            "is_installed": False,
            "uninstalled_at": "now()",
        }).eq("id", plugin_id).execute()
        
        return {"status": "uninstalled"}
    except Exception as e:
        logger.error(f"[community] uninstall plugin failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to uninstall plugin: {str(e)}")


@router.put("/community/plugins/{plugin_id}", tags=["community"])
async def update_plugin(
    plugin_id: str,
    req: PluginUpdate,
    _: None = Depends(verify_key),
):
    """Update plugin configuration."""
    try:
        supabase = db.get_db()
        update_data = {k: v for k, v in req.model_dump().items() if v is not None}
        res = supabase.table("plugins").update(update_data).eq("id", plugin_id).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[community] update plugin failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update plugin: {str(e)}")


# ─── Documentation Site Generator ─────────────────────────────────────────

@router.get("/community/docs/generate", tags=["community"])
async def generate_documentation(_: None = Depends(verify_key)):
    """Generate documentation site content from API spec and knowledge graph."""
    try:
        supabase = db.get_db()
        
        # Get documentation nodes from knowledge graph
        docs = supabase.table("nodes").select("title, body, created_at").eq(
            "type", "documentation"
        ).eq("status", "published").execute()
        
        # Get API endpoints
        from main import app
        endpoints = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "DELETE"):
                        endpoints.append({
                            "method": method,
                            "path": route.path,
                        })
        
        return {
            "documentation_pages": len(docs.data or []),
            "api_endpoints": len(endpoints),
            "docs": docs.data or [],
            "endpoints": endpoints,
            "generated_at": "now()",
        }
    except Exception as e:
        logger.error(f"[community] generate docs failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate docs: {str(e)}")


# ─── Community Stats ──────────────────────────────────────────────────────

@router.get("/community/stats", tags=["community"])
async def get_community_stats(_: None = Depends(verify_key)):
    """Get community and ecosystem statistics."""
    try:
        supabase = db.get_db()
        
        # Plugin stats
        plugins = supabase.table("plugins").select("id", count="exact").execute()
        plugin_count = plugins.count if hasattr(plugins, 'count') else len(plugins.data or [])
        
        installed = supabase.table("plugins").select("id", count="exact").eq("is_installed", True).execute()
        installed_count = installed.count if hasattr(installed, 'count') else len(installed.data or [])
        
        # Documentation stats
        docs = supabase.table("nodes").select("id", count="exact").eq("type", "documentation").execute()
        doc_count = docs.count if hasattr(docs, 'count') else len(docs.data or [])
        
        return {
            "total_plugins": plugin_count,
            "installed_plugins": installed_count,
            "documentation_pages": doc_count,
            "api_endpoints": 0,  # Would need to count from app.routes
            "status": "growing",
        }
    except Exception as e:
        logger.error(f"[community] stats failed: {e}")
        return {"error": str(e)}


# ─── Example Projects ─────────────────────────────────────────────────────

@router.get("/community/examples", tags=["community"])
async def list_example_projects(_: None = Depends(verify_key)):
    """List example projects built with DAWN."""
    examples = [
        {
            "name": "DAWN Chat Interface",
            "description": "The main chat interface for interacting with DAWN",
            "type": "core",
            "technologies": ["Next.js", "TypeScript", "Tailwind"],
            "path": "dawn-ui/src/app/chat",
        },
        {
            "name": "Knowledge Graph Explorer",
            "description": "Visual explorer for the knowledge graph",
            "type": "core",
            "technologies": ["Next.js", "D3.js", "Supabase"],
            "path": "dawn-ui/src/app/nodes",
        },
        {
            "name": "SSH Remote Manager",
            "description": "Manage SSH hosts and execute remote commands",
            "type": "tool",
            "technologies": ["FastAPI", "Paramiko", "React"],
            "path": "dawn-api/routers/ssh_hosts.py",
        },
        {
            "name": "OSINT Recon Tool",
            "description": "OSINT target management and reconnaissance",
            "type": "tool",
            "technologies": ["FastAPI", "Shodan", "Python"],
            "path": "dawn-api/routers/osint.py",
        },
        {
            "name": "Pentesting Dashboard",
            "description": "Security scanning and vulnerability management",
            "type": "tool",
            "technologies": ["FastAPI", "Nmap", "React"],
            "path": "dawn-api/routers/pentest.py",
        },
        {
            "name": "Business Intelligence Dashboard",
            "description": "BI dashboards and automated reporting",
            "type": "business",
            "technologies": ["FastAPI", "Pandas", "React"],
            "path": "dawn-api/routers/bi.py",
        },
        {
            "name": "Monitoring & Alerting",
            "description": "Infrastructure monitoring with alert rules",
            "type": "infrastructure",
            "technologies": ["FastAPI", "HTTPX", "React"],
            "path": "dawn-api/routers/monitoring.py",
        },
        {
            "name": "Document Management",
            "description": "Document editor with version history and templates",
            "type": "productivity",
            "technologies": ["FastAPI", "Markdown", "React"],
            "path": "dawn-api/routers/documents.py",
        },
    ]
    
    return examples
