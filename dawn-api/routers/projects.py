"""
Projects API — define goals/projects and see related content.

A project groups related work (e.g. "Marketing X"). Projects carry a `tags`
array; artifacts, memories, and nodes can be associated to a project by
sharing one of those tags. The related-content endpoints return everything
tagged with the project's tags so you can see all work in one place.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, field_validator
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    status: str = "active"
    priority: str = "medium"
    tags: list[str] = []

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in ("active", "paused", "completed", "cancelled"):
            raise ValueError("status must be active/paused/completed/cancelled")
        return v

    @field_validator("priority")
    @classmethod
    def _priority(cls, v: str) -> str:
        if v not in ("low", "medium", "high", "critical"):
            raise ValueError("priority must be low/medium/high/critical")
        return v


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    tags: Optional[list[str]] = None


@router.get("/projects", tags=["projects"])
async def list_projects(_: None = Depends(verify_key)):
    """List all projects, most recent first."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("projects").select(
            "id, name, description, status, priority, tags, created_at, updated_at"
        ).order("updated_at", desc=True).execute())
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects", tags=["projects"])
async def create_project(req: ProjectCreate, _: None = Depends(verify_key)):
    """Create a new project."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("projects").insert(
            req.model_dump()
        ).execute())
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create project")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}", tags=["projects"])
async def get_project(project_id: str, _: None = Depends(verify_key)):
    """Get a single project."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("projects").select(
            "*"
        ).eq("id", project_id).execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Project not found")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/projects/{project_id}", tags=["projects"])
async def update_project(project_id: str, req: ProjectUpdate, _: None = Depends(verify_key)):
    """Update a project."""
    try:
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("projects").update(
            data
        ).eq("id", project_id).execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="Project not found")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}", tags=["projects"])
async def delete_project(project_id: str, _: None = Depends(verify_key)):
    """Delete a project."""
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("projects").delete().eq("id", project_id).execute())
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/related", tags=["projects"])
async def get_project_related(project_id: str, _: None = Depends(verify_key)):
    """Return everything related to a project (by shared tags): artifacts,
    memories, nodes, and chat sessions."""
    try:
        supabase = db.get_db()
        proj_res = await db._async_execute(lambda: supabase.table("projects").select(
            "id, name, tags"
        ).eq("id", project_id).execute())
        if not proj_res.data:
            raise HTTPException(status_code=404, detail="Project not found")
        project = proj_res.data[0]
        tags = project.get("tags") or []

        result = {"project": project, "artifacts": [], "memories": [], "nodes": [], "sessions": []}

        if tags:
            # Artifacts with any matching tag
            art_res = await db._async_execute(lambda: supabase.table("artifacts").select(
                "id, title, type, description, created_at"
            ).overlaps("tags", tags).order("created_at", desc=True).limit(50).execute())
            result["artifacts"] = art_res.data or []

            # Memories with any matching tag
            mem_res = await db._async_execute(lambda: supabase.table("memories").select(
                "id, title, body, fact_type, confidence, created_at"
            ).eq("status", "active").overlaps("tags", tags).order("created_at", desc=True).limit(50).execute())
            result["memories"] = mem_res.data or []

            # Nodes tagged with any matching tag
            node_res = await db._async_execute(lambda: supabase.table("nodes").select(
                "id, title, type, status, created_at"
            ).eq("status", "active").overlaps("tags", tags).order("created_at", desc=True).limit(50).execute())
            result["nodes"] = node_res.data or []

            # Chat sessions whose title mentions the project name
            sess_res = await db._async_execute(lambda: supabase.table("chat_sessions").select(
                "id, title, created_at, updated_at"
            ).ilike("title", f"%{project['name']}%").order("updated_at", desc=True).limit(50).execute())
            result["sessions"] = sess_res.data or []

        return result
    except Exception as e:
        logger.error(f"Failed to get project related content: {e}")
        raise HTTPException(status_code=500, detail=str(e))
