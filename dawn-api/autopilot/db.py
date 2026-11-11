"""Autopilot DB access — jobs, runs, events over Supabase REST."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import db.client as db

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def list_jobs(enabled_only: bool = False) -> list[dict]:
    supabase = db.get_db()
    q = supabase.table("autopilot_jobs").select("*").order("name")
    if enabled_only:
        q = q.eq("enabled", True)
    res = await db._async_execute(lambda: q.execute())
    return res.data or []


async def get_job(job_id: str) -> Optional[dict]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_jobs").select("*").eq("id", job_id).maybe_single().execute()
    )
    return res.data if res and res.data else None


async def create_job(data: dict) -> Optional[dict]:
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("autopilot_jobs").insert(data).execute())
    return (res.data or [{}])[0] if res.data else None


async def update_job(job_id: str, data: dict) -> Optional[dict]:
    supabase = db.get_db()
    data["updated_at"] = "now()"
    res = await db._async_execute(lambda: supabase.table("autopilot_jobs").update(data).eq("id", job_id).execute())
    return (res.data or [{}])[0] if res.data else None


async def delete_job(job_id: str) -> None:
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("autopilot_jobs").delete().eq("id", job_id).execute())


async def create_run(run: dict) -> Optional[dict]:
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("autopilot_runs").insert(run).execute())
    return (res.data or [{}])[0] if res.data else None


async def update_run(run_id: str, data: dict) -> None:
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("autopilot_runs").update(data).eq("id", run_id).execute())


async def get_run(run_id: str) -> Optional[dict]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("*").eq("id", run_id).maybe_single().execute()
    )
    return res.data if res and res.data else None


async def list_runs(job_id: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 50, offset: int = 0, order_desc: bool = True) -> list[dict]:
    supabase = db.get_db()
    q = supabase.table("autopilot_runs").select("*")
    if job_id:
        q = q.eq("job_id", job_id)
    if status:
        q = q.eq("status", status)
    q = q.order("created_at", desc=order_desc).limit(limit).offset(offset)
    res = await db._async_execute(lambda: q.execute())
    return res.data or []


async def running_runs() -> list[dict]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("*").eq("status", "running").execute()
    )
    return res.data or []


async def recent_findings(job_id: str, since_hours: int) -> list[dict]:
    """Findings already reported by this job (for dedupe)."""
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("findings").eq("job_id", job_id)
        .gte("created_at", f"now() - interval '{int(since_hours)} hours'")
        .execute()
    )
    out = []
    for row in res.data or []:
        out.extend(row.get("findings") or [])
    return out


async def claim_due_job(job_id: str, old_next: str, new_next: str) -> Optional[dict]:
    """Atomic claim: only succeeds if next_run_at still equals the value we
    computed. Returns the claimed row, or None if another worker got it."""
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_jobs")
        .update({"next_run_at": new_next, "last_run_at": "now()"})
        .eq("id", job_id)
        .eq("next_run_at", old_next)
        .execute()
    )
    return (res.data or [{}])[0] if res.data else None


async def set_cancel_all() -> None:
    supabase = db.get_db()
    await db._async_execute(
        lambda: supabase.table("autopilot_runs").update({"cancel_requested": True})
        .eq("status", "running").execute()
    )


async def publish_event(etype: str, payload: Optional[dict] = None) -> Optional[str]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_events").insert(
            {"type": etype, "payload": payload or {}}
        ).execute()
    )
    if res.data:
        return res.data[0]["id"]
    return None


async def pending_events(limit: int = 100) -> list[dict]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_events").select("*")
        .is_("processed_at", "null").order("created_at").limit(limit).execute()
    )
    return res.data or []


async def mark_event_processed(event_id: str) -> None:
    supabase = db.get_db()
    await db._async_execute(
        lambda: supabase.table("autopilot_events").update({"processed_at": "now()"}).eq("id", event_id).execute()
    )


async def stats_today() -> dict:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("status, est_cost, tokens_out")
        .gte("created_at", "now() - interval '24 hours'")
        .execute()
    )
    rows = res.data or []
    quiet = sum(1 for r in rows if r.get("status") == "quiet")
    tokens = sum((r.get("tokens_out") or 0) for r in rows)
    cost = sum((r.get("est_cost") or 0) for r in rows)
    return {"runs_today": len(rows), "quiet": quiet, "tokens_today": tokens, "cost_today": cost}


async def all_running_jobs() -> int:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("id", count="exact").eq("status", "running").execute()
    )
    return getattr(res, "count", 0) or 0
