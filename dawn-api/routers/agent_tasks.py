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


class AgentTaskFollowUp(BaseModel):
    follow_up: str


@router.post("/agent-tasks/{task_id}/follow-up", tags=["agent-tasks"])
async def follow_up_agent_task(task_id: str, req: AgentTaskFollowUp, _: None = Depends(verify_key)):
    """Run a follow-up on a completed agent task.

    Re-runs the agent loop with the task's original goal plus its prior result
    as context, then updates the task's result with the follow-up answer. This
    gives a way to continue a task after it's marked complete.
    """
    import asyncio
    from llm.identity import resolve_identity
    from llm.agent import run_agent_loop

    try:
        supabase = db.get_db()
        res = supabase.table("agent_tasks").select("*").eq("id", task_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Task not found")
        task = res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    goal = task.get("goal") or ""
    prior_result = task.get("result") or ""
    max_iterations = task.get("max_iterations") or 50

    # Build a follow-up prompt grounded in the original goal and prior result.
    prompt = (
        f"Follow-up on an earlier agent task.\n\n"
        f"Original goal: {goal}\n\n"
        f"Previous result:\n{prior_result or '(none)'}\n\n"
        f"Follow-up request: {req.follow_up}\n\n"
        f"Continue the work and provide a complete, updated answer."
    )

    key = getattr(settings, "dawn_api_key", None) or "dev-key"
    identity = resolve_identity(key)

    final_content = ""
    error = None
    try:
        async for event in run_agent_loop(
            user_message=prompt,
            identity=identity,
            history=[],
            max_iterations=max_iterations,
        ):
            etype = event.get("type")
            if etype == "token":
                final_content = event.get("content", "")
            elif etype == "done":
                final_content = event.get("content", "")
            elif etype == "error":
                error = event.get("content", "Agent loop error")
            elif etype == "iteration_limit":
                error = event.get("content", "Iteration limit reached")
    except Exception as e:
        logger.exception(f"Agent task follow-up failed for {task_id}")
        error = str(e)

    status = "completed" if not error else "failed"
    try:
        supabase.table("agent_tasks").update({
            "status": status,
            "result": final_content or None,
            "error": error,
            "follow_up": req.follow_up,
        }).eq("id", task_id).execute()
    except Exception as e:
        logger.error(f"Failed to update task after follow-up: {e}")

    return {
        "id": task_id,
        "status": status,
        "result": final_content,
        "error": error,
    }


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
