"""
Autonomous agent-task scheduler.

Runs due `agent_schedules` on a cron/interval basis and executes each due
schedule's goal through the agent loop autonomously. Results are:
  - recorded as an `agent_tasks` row (status running -> completed/failed),
  - logged to `agent_logs` so they surface on the Dashboard activity feed,
  - (optionally) persisted as artifacts so they land on the Canvas.

This is the runner that `routers/agent_tasks.py`'s schedule CRUD has been
waiting for — previously there was no background process executing schedules.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from llm.identity import resolve_identity, TrustTier
from llm.agent import run_agent_loop
import db.client as db

logger = logging.getLogger(__name__)

# How often the scheduler checks for due schedules (seconds).
POLL_INTERVAL_SECONDS = 60


def _owner_identity():
    """Resolve an owner-tier identity for autonomous runs. Falls back to the
    legacy shared key so the scheduler works even before DAWN_API_KEYS is set."""
    key = getattr(settings, "dawn_api_key", None) or "dev-key"
    identity = resolve_identity(key)
    if identity.tier == TrustTier.UNKNOWN:
        # Last resort: build an owner identity directly from the shared key.
        return resolve_identity(key) if key else None
    return identity


async def _get_due_schedules() -> list[dict]:
    """Return active schedules whose cron is due. For simplicity and
    determinism we treat each schedule as due once per poll interval — a real
    cron evaluator can be swapped in later. `last_run_at` guards against
    re-running within the same minute."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("agent_schedules")
            .select("*")
            .eq("is_active", True)
            .execute())
        now = datetime.now(timezone.utc)
        due = []
        for s in res.data or []:
            last = s.get("last_run_at")
            if last:
                try:
                    last_dt = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
                    # Only run at most once per minute.
                    if (now - last_dt).total_seconds() < 60:
                        continue
                except Exception:
                    pass
            due.append(s)
        return due
    except Exception as e:
        logger.error(f"[AgentScheduler] Failed to load schedules: {e}")
        return []


async def _run_schedule(schedule: dict) -> None:
    """Execute a single schedule's goal through the agent loop."""
    schedule_id = schedule["id"]
    goal = schedule.get("task_goal") or schedule.get("goal") or ""
    max_iterations = schedule.get("max_iterations") or 50

    if not goal:
        logger.warning(f"[AgentScheduler] Schedule {schedule_id} has no goal — skipping")
        return

    logger.info(f"[AgentScheduler] Running schedule '{schedule.get('name')}' — {goal}")

    # Create an agent_tasks row to track this run.
    task_id = None
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("agent_tasks").insert({
            "goal": goal,
            "max_iterations": max_iterations,
            "status": "running",
            "progress": 0,
            "iterations": 0,
            "tools_used": [],
        }).execute())
        if res.data:
            task_id = res.data[0]["id"]
    except Exception as e:
        logger.error(f"[AgentScheduler] Failed to create task row: {e}")

    # Run the agent loop, collecting the final answer.
    final_content = ""
    iterations = 0
    tools_used: list[str] = []
    error = None
    try:
        identity = _owner_identity()
        if identity is None:
            raise RuntimeError("No owner identity available for autonomous run")

        async for event in run_agent_loop(
            user_message=goal,
            identity=identity,
            history=[],
            max_iterations=max_iterations,
        ):
            etype = event.get("type")
            if etype == "tool_call":
                name = event.get("name")
                if name and name not in tools_used:
                    tools_used.append(name)
            elif etype == "token":
                final_content = event.get("content", "")
            elif etype == "done":
                final_content = event.get("content", "")
                iterations = event.get("iterations", iterations)
            elif etype == "error":
                error = event.get("content", "Agent loop error")
            elif etype == "iteration_limit":
                error = event.get("content", "Iteration limit reached")
    except Exception as e:
        logger.exception(f"[AgentScheduler] Agent loop failed for schedule {schedule_id}")
        error = str(e)

    status = "completed" if not error else "failed"
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("agent_tasks").update({
            "status": status,
            "progress": 100 if status == "completed" else 0,
            "iterations": iterations,
            "tools_used": tools_used,
        }).eq("id", task_id).execute() if task_id else None)
    except Exception as e:
        logger.error(f"[AgentScheduler] Failed to update task row: {e}")

    # Log to agent_logs so it surfaces on the Dashboard activity feed.
    # NOTE: agent_logs uses a different status vocabulary ('success'/'error')
    # than agent_tasks ('completed'/'failed') — matching the DB check
    # constraint agent_logs_status_check and the frontend's AgentLogEntry type.
    log_status = "success" if not error else "error"
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("agent_logs").insert({
            "status": log_status,
            "task": goal,
            "tools_used": tools_used,
            "tokens_used": 0,
            "model": settings.deepseek_model,
            "error_message": error,
        }).execute())
    except Exception as e:
        logger.error(f"[AgentScheduler] Failed to log agent run: {e}")

    # Update schedule metadata.
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("agent_schedules").update({
            "last_run_at": "now()",
            "next_run_at": None,
        }).eq("id", schedule_id).execute())
    except Exception as e:
        logger.error(f"[AgentScheduler] Failed to update schedule: {e}")

    logger.info(f"[AgentScheduler] Schedule '{schedule.get('name')}' -> {status}")


async def run_due_schedules() -> None:
    """Run every due schedule once."""
    due = await _get_due_schedules()
    if not due:
        return
    logger.info(f"[AgentScheduler] {len(due)} schedule(s) due")
    for schedule in due:
        try:
            await _run_schedule(schedule)
        except Exception as e:
            logger.exception(f"[AgentScheduler] Failed to run schedule {schedule.get('id')}: {e}")


async def scheduler_loop() -> None:
    """Background loop: poll for due schedules every POLL_INTERVAL_SECONDS.

    Runs as an asyncio task on the app's main event loop (not a separate
    APScheduler thread). This avoids the cross-thread event-loop conflicts that
    froze the app, and a single long-running task can't overlap itself the way
    an interval job does ("maximum number of running instances reached").
    """
    logger.info(f"[AgentScheduler] Autonomous scheduler started (poll every {POLL_INTERVAL_SECONDS}s)")
    while True:
        try:
            await run_due_schedules()
        except Exception as e:
            logger.exception(f"[AgentScheduler] Poll cycle failed: {e}")
        # Refresh dashboard alerts (aging approvals, failed tasks) so AlertStrip
        # has a live source without a separate process.
        try:
            from tools.alerts import write_alerts
            await write_alerts()
        except Exception as e:
            logger.exception(f"[AgentScheduler] Alert write cycle failed: {e}")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# The running scheduler task, so it can be cancelled on shutdown.
_scheduler_task: Optional[asyncio.Task] = None


def start_agent_scheduler() -> Optional[object]:
    """Start the autonomous scheduler as an asyncio task on the current event
    loop. Returns a handle with start()/stop() semantics for shutdown.

    Runs `scheduler_loop` on the app's main event loop via asyncio.create_task,
    matching the ingestion-queue worker pattern. This keeps all DB/LLM calls
    on the loop they were created for, avoiding the freeze caused by running
    `asyncio.run()` in a separate APScheduler thread.
    """
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        logger.info("[AgentScheduler] Scheduler already running")
        return _scheduler_task
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        logger.error("[AgentScheduler] No running event loop — scheduler not started")
        return None
    _scheduler_task = loop.create_task(scheduler_loop())
    logger.info("[AgentScheduler] Autonomous scheduler task started")
    return _scheduler_task


async def stop_agent_scheduler() -> None:
    """Cancel the running scheduler task (called on shutdown)."""
    global _scheduler_task
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
        logger.info("[AgentScheduler] Autonomous scheduler stopped")
