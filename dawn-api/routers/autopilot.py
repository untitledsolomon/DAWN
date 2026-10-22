"""Autopilot API — jobs, runs, master switch, kill, schedule preview, events."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from config import settings as app_settings
from runtime_settings import get_runtime
from autopilot import db, engine

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class JobCreate(BaseModel):
    name: str
    goal: str
    description: Optional[str] = None
    autonomy: str = "observe"
    schedule: Optional[dict] = None
    triggers: list[dict] = []
    preflight: list[dict] = []
    preflight_mode: str = "any"
    tool_allowlist: list[str] = []
    model: Optional[str] = None
    limits: dict = {}
    notify: dict = {}
    retry: dict = {}
    dedupe_hours: int = 24


class JobPatch(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    description: Optional[str] = None
    autonomy: Optional[str] = None
    enabled: Optional[bool] = None
    schedule: Optional[dict] = None
    triggers: Optional[list[dict]] = None
    preflight: Optional[list[dict]] = None
    preflight_mode: Optional[str] = None
    tool_allowlist: Optional[list[str]] = None
    model: Optional[str] = None
    limits: Optional[dict] = None
    notify: Optional[dict] = None
    retry: Optional[dict] = None
    dedupe_hours: Optional[int] = None


class RunRequest(BaseModel):
    dry_run: bool = False


class FeedbackBody(BaseModel):
    feedback: str


class EventBody(BaseModel):
    type: str
    payload: dict = {}


class PreviewBody(BaseModel):
    schedule: dict


def _validate_schedule(schedule: dict) -> Optional[str]:
    """Return an error string when the schedule is invalid (min-interval floor)."""
    if not isinstance(schedule, dict):
        return "schedule must be an object"
    cron = schedule.get("cron")
    if not cron or not isinstance(cron, str):
        return "schedule.cron is required"
    try:
        from croniter import croniter
        croniter(cron, datetime.now(timezone.utc))
    except Exception:
        return f"invalid cron expression '{cron}'"

    # Hard floor: schedules shorter than autopilot.min_interval_minutes are
    # rejected with a clear message (spec 5.2).
    min_interval = int(get_runtime().get("autopilot.min_interval_minutes") or 5)
    if min_interval and cron.strip() != "* * * * *":
        try:
            import re
            m = re.match(r"^\*\s+\*/(\d+)(?:[,\s].*)?$", cron.strip())
            if m:
                minutes = int(m.group(1))
                if minutes < min_interval:
                    return f"schedule fires every {minutes}m — below the {min_interval}m minimum"
        except Exception:
            pass
    return None


def _compute_next_run_from(schedule: dict, base) -> list[str]:
    try:
        from croniter import croniter
        it = croniter(schedule.get("cron"), base)
        return [(it.get_next(datetime).astimezone(timezone.utc)).isoformat() for _ in range(5)]
    except Exception:
        return []


@router.get("/autopilot/status", tags=["autopilot"])
async def autopilot_status(_: None = Depends(verify_key)):
    rt = get_runtime()
    stats = await db.stats_today()
    running = await db.all_running_jobs()
    return {"enabled": bool(rt.get("autopilot.enabled")), "running": running, **stats}


@router.post("/autopilot/kill", tags=["autopilot"])
async def autopilot_kill(_: None = Depends(verify_key)):
    rt = get_runtime()
    await rt.set("autopilot.enabled", False, by="autopilot", reason="kill switch")
    await db.set_cancel_all()
    return {"ok": True, "status": "stopped"}


@router.get("/autopilot/jobs", tags=["autopilot"])
async def list_jobs(_: None = Depends(verify_key)):
    jobs = await db.list_jobs()
    for j in jobs:
        j.pop("goal", None)
    return jobs


@router.post("/autopilot/jobs", tags=["autopilot"])
async def create_job(req: JobCreate, _: None = Depends(verify_key)):
    if req.schedule:
        err = _validate_schedule(req.schedule)
        if err:
            raise HTTPException(status_code=422, detail=err)
    data = req.model_dump()
    data["enabled"] = False
    data["autonomy"] = "observe" if req.autonomy not in ("observe", "propose") else req.autonomy
    if req.schedule and req.schedule.get("cron"):
        from autopilot.scheduler import _compute_next_run
        data["next_run_at"] = _compute_next_run(data, datetime.now(timezone.utc))
    job = await db.create_job(data)
    if not job:
        raise HTTPException(status_code=500, detail="Failed to create job")
    return {"id": job["id"], "name": job["name"], "enabled": False}


@router.get("/autopilot/jobs/{job_id}", tags=["autopilot"])
async def get_job(job_id: str, _: None = Depends(verify_key)):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/autopilot/jobs/{job_id}", tags=["autopilot"])
async def patch_job(job_id: str, req: JobPatch, _: None = Depends(verify_key)):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    if "schedule" in data and data["schedule"]:
        err = _validate_schedule(data["schedule"])
        if err:
            raise HTTPException(status_code=422, detail=err)
    # next_run_at is computed when a job is enabled or its schedule changes.
    wants_recompute = "schedule" in data or (data.get("enabled") is True and not job.get("enabled"))
    if wants_recompute and (data.get("schedule") or job.get("schedule")):
        from autopilot.scheduler import _compute_next_run
        merged = {**job, **data}
        data["next_run_at"] = _compute_next_run(merged, datetime.now(timezone.utc))
    updated = await db.update_job(job_id, data)
    return updated or {"id": job_id}


@router.delete("/autopilot/jobs/{job_id}", tags=["autopilot"])
async def delete_job(job_id: str, _: None = Depends(verify_key)):
    await db.delete_job(job_id)
    return {"status": "deleted"}


@router.post("/autopilot/jobs/{job_id}/run", tags=["autopilot"])
async def run_job(job_id: str, req: RunRequest, _: None = Depends(verify_key)):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run, status = await engine.run_job(job, triggered_by="manual", dry_run=req.dry_run)
    return {"run_id": run["id"], "status": status}


@router.post("/autopilot/jobs/{job_id}/pause", tags=["autopilot"])
async def pause_job(job_id: str, _: None = Depends(verify_key)):
    updated = await db.update_job(job_id, {"paused_reason": "paused by user"})
    return {"status": "paused"}


@router.post("/autopilot/jobs/{job_id}/resume", tags=["autopilot"])
async def resume_job(job_id: str, _: None = Depends(verify_key)):
    updated = await db.update_job(job_id, {"paused_reason": None, "consecutive_failures": 0})
    return {"status": "resumed"}


@router.get("/autopilot/runs", tags=["autopilot"])
async def list_runs(job_id: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 50, offset: int = 0, _: None = Depends(verify_key)):
    return await db.list_runs(job_id, status, limit, offset)


@router.get("/autopilot/runs/{run_id}", tags=["autopilot"])
async def get_run(run_id: str, _: None = Depends(verify_key)):
    run = await db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.post("/autopilot/runs/{run_id}/cancel", tags=["autopilot"])
async def cancel_run(run_id: str, _: None = Depends(verify_key)):
    await db.update_run(run_id, {"cancel_requested": True})
    return {"status": "cancel requested"}


@router.post("/autopilot/runs/{run_id}/feedback", tags=["autopilot"])
async def run_feedback(run_id: str, body: FeedbackBody, _: None = Depends(verify_key)):
    if body.feedback not in ("useful", "noise"):
        raise HTTPException(status_code=422, detail="feedback must be 'useful' or 'noise'")
    await db.update_run(run_id, {"feedback": body.feedback})
    return {"status": "recorded"}


@router.post("/autopilot/preview-schedule", tags=["autopilot"])
async def preview_schedule(body: PreviewBody, _: None = Depends(verify_key)):
    err = _validate_schedule(body.schedule)
    if err:
        raise HTTPException(status_code=422, detail=err)
    nexts = _compute_next_run_from(body.schedule, datetime.now(timezone.utc))
    return {"human": body.schedule.get("cron"), "next": nexts, "warnings": []}


@router.post("/autopilot/events", tags=["autopilot"])
async def publish_event(body: EventBody, _: None = Depends(verify_key)):
    event_id = await db.publish_event(body.type, body.payload)
    return {"id": event_id}
