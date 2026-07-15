"""
Advanced Agent Tasks — persistent, multi-step, scheduled agent execution.
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


class AgentTaskCreate(BaseModel):
    goal: str
    parent_task_id: Optional[str] = None
    max_iterations: int = 100


class AgentScheduleCreate(BaseModel):
    name: str
    task_goal: str
    cron_expression: str
    max_iterations: int = 50


@router.get("/agent-tasks", tags=["agent-tasks"])
async def list_agent_tasks(status: Optional[str] = None, limit: int = 50, _: None = Depends(verify_key)):
    """List agent tasks."""
    try:
        supabase = db.get_db()
        q = supabase.table("agent_tasks").select("*").order("created_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list agent tasks: {e}")
        return []


@router.post("/agent-tasks", tags=["agent-tasks"])
async def create_agent_task(req: AgentTaskCreate, _: None = Depends(verify_key)):
    """Create a new agent task."""
    try:
        supabase = db.get_db()
        res = supabase.table("agent_tasks").insert({
            "goal": req.goal,
            "parent_task_id": req.parent_task_id,
            "max_iterations": req.max_iterations,
            "status": "pending",
        }).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create task")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent-tasks/{task_id}", tags=["agent-tasks"])
async def get_agent_task(task_id: str, _: None = Depends(verify_key)):
    """Get a single agent task."""
    try:
        supabase = db.get_db()
        res = supabase.table("agent_tasks").select("*").eq("id", task_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Task not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent-tasks/{task_id}/cancel", tags=["agent-tasks"])
async def cancel_agent_task(task_id: str, _: None = Depends(verify_key)):
    """Cancel an agent task."""
    try:
        supabase = db.get_db()
        supabase.table("agent_tasks").update({
            "status": "cancelled",
        }).eq("id", task_id).execute()
        return {"status": "cancelled"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent-tasks/{task_id}/resume", tags=["agent-tasks"])
async def resume_agent_task(task_id: str, _: None = Depends(verify_key)):
    """Resume a paused agent task."""
    try:
        supabase = db.get_db()
        supabase.table("agent_tasks").update({
            "status": "running",
        }).eq("id", task_id).execute()
        return {"status": "resumed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agent-schedules", tags=["agent-tasks"])
async def list_agent_schedules(_: None = Depends(verify_key)):
    """List agent schedules."""
    try:
        supabase = db.get_db()
        res = supabase.table("agent_schedules").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list agent schedules: {e}")
        return []


@router.post("/agent-schedules", tags=["agent-tasks"])
async def create_agent_schedule(req: AgentScheduleCreate, _: None = Depends(verify_key)):
    """Create a new agent schedule."""
    try:
        supabase = db.get_db()
        res = supabase.table("agent_schedules").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create schedule")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agent-schedules/{schedule_id}", tags=["agent-tasks"])
async def delete_agent_schedule(schedule_id: str, _: None = Depends(verify_key)):
    """Delete an agent schedule."""
    try:
        supabase = db.get_db()
        supabase.table("agent_schedules").delete().eq("id", schedule_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
