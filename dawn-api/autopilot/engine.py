"""
Autopilot run engine — wraps run_agent_loop with budgets, policies and DB
recording. A job run is always recorded, including runs that never called the
model (quiet outcomes with zero LLM calls).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from runtime_settings import get_runtime
from autopilot import db
from autopilot.policy import RunBudget, RunPolicy
from llm.engine import usage_cost
from llm.agent import run_agent_loop

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("completed", "quiet", "needs_attention", "failed", "budget_stopped", "cancelled")


def _owner_identity():
    from llm.identity import resolve_identity
    from config import settings
    key = getattr(settings, "dawn_api_key", None) or "dev-key"
    return resolve_identity(key)


def _fingerprint(item: dict) -> str:
    title = (item.get("title") or "").strip().lower()
    ref = item.get("ref") or ""
    return f"{title}|{ref}"


def _state_context(job: dict) -> str:
    state = job.get("state") or {}
    if not state:
        return ""
    try:
        return json.dumps({"state": state, "reported_at": state.get("_at")}, default=str)[:2000]
    except Exception:
        return ""


async def run_job(
    job: dict,
    triggered_by: str = "manual",
    dry_run: bool = False,
    cancel_flag: Optional[dict] = None,
) -> tuple[dict, str]:
    """Execute one job. Returns (run_row, status). `cancel_flag` is a shared
    mutable dict holding {'cancel': bool} so the UI Stop can cancel a run."""
    if cancel_flag is None:
        cancel_flag = {"cancel": False}

    run = await db.create_run({
        "job_id": job["id"],
        "triggered_by": "dry_run" if dry_run else triggered_by,
        "status": "queued",
        "cancel_requested": False,
    })
    run_id = run["id"]

    rt = get_runtime().snapshot(prefix="autopilot.")
    limits = job.get("limits") or {}
    max_steps = int(limits.get("max_steps") or rt.get("autopilot.default_max_steps"))
    max_tokens = int(limits.get("max_tokens") or rt.get("autopilot.default_max_tokens"))
    max_seconds = int(limits.get("max_seconds") or rt.get("autopilot.default_max_seconds"))

    mode = job.get("autonomy") or "observe"
    if dry_run:
        mode = "observe"
    policy = RunPolicy(
        mode=mode,
        allowlist=set(job.get("tool_allowlist") or []),
        requested_by=f"autopilot:{job['id']}:{run_id}",
    )

    def _cancelled() -> bool:
        return bool(cancel_flag.get("cancel"))

    budget = RunBudget(max_steps=max_steps, max_tokens=max_tokens, max_seconds=max_seconds, cancelled=_cancelled)

    tokens_in = 0
    tokens_out = 0
    step_count = 0
    tools_used: list[str] = []
    findings_events: list[dict] = []
    last_report: Optional[dict] = None
    summary_text = ""
    status = "completed"
    error_class: Optional[str] = None
    error: Optional[str] = None

    def _on_usage(usage: dict) -> None:
        nonlocal tokens_in, tokens_out
        tokens_in += int(usage.get("prompt_tokens") or 0)
        tokens_out += int(usage.get("completion_tokens") or 0)

    try:
        await db.update_run(run_id, {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()})
        async for event in run_agent_loop(
            user_message=job.get("goal") or "",
            identity=_owner_identity(),
            history=[],
            max_iterations=None,
            memory_context=_state_context(job),
            budget=budget,
            policy=policy,
            stop_on_tools={"autopilot_report"},
            on_usage=_on_usage,
        ):
            etype = event.get("type")
            if etype == "tool_result":
                name = event.get("name")
                if name and name not in tools_used:
                    tools_used.append(name)
                if name == "autopilot_report" and isinstance(event.get("output"), dict):
                    last_report = event["output"]
            elif etype in ("done", "token"):
                summary_text = event.get("content") or summary_text
            elif etype == "budget_stopped":
                status = "budget_stopped"
                error_class = f"budget.{event.get('kind')}"
                error = event.get("content")
                summary_text = event.get("content") or summary_text
            elif etype == "needs_attention":
                status = "needs_attention"
                error = event.get("content")
            elif etype == "error":
                status = "failed"
                error_class = "agent.loop"
                error = event.get("content")
            elif etype == "iteration_limit":
                status = "failed"
                error_class = "steps"
                error = event.get("content")
            step_count += 1
    except Exception as e:
        logger.exception(f"[autopilot] run {run_id} crashed")
        status = "failed"
        error_class = "run.error"
        error = str(e)

    if _cancelled():
        status = "cancelled"
        error_class = "cancelled"
        error = "Run cancelled by user."

    # Structured finish: autopilot_report output is the source of truth.
    if last_report is not None and last_report.get("status"):
        items = last_report.get("items") or []
        summary_text = last_report.get("summary") or summary_text
        if not isinstance(items, list):
            items = []
        findings_events = items
        rs = last_report.get("status")
        if rs == "quiet":
            status = "quiet"
        elif rs == "blocked":
            status = "needs_attention"
            error_class = error_class or "blocked"

    # Dedupe findings against what this job already reported.
    findings = findings_events
    if findings and not dry_run:
        try:
            dedupe_hours = int(job.get("dedupe_hours") or 24)
            seen = {_fingerprint(x) for x in await db.recent_findings(job["id"], dedupe_hours)}
            kept = [f for f in findings if _fingerprint(f) not in seen]
            if kept and len(kept) < len(findings):
                logger.info(f"[autopilot] run {run_id}: deduped {len(findings) - len(kept)} repeat item(s)")
            if not kept and findings:
                status = "quiet"
            findings = kept
        except Exception:
            logger.exception("[autopilot] dedupe failed")

    est = usage_cost({"prompt_tokens": tokens_in, "completion_tokens": tokens_out})
    await db.update_run(run_id, {
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "steps": step_count,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "est_cost": est,
        "model": None,
        "summary": summary_text or None,
        "findings": findings,
        "tools_used": tools_used,
        "error_class": error_class,
        "error": error,
    })

    # Update job state (what was last reported and when) — not in dry runs.
    if not dry_run:
        try:
            state = dict(job.get("state") or {})
            state["_summary"] = summary_text[:2000]
            state["_status"] = status
            state["_at"] = datetime.now(timezone.utc).isoformat()
            await db.update_job(job["id"], {"state": state})
        except Exception:
            logger.exception("[autopilot] state update failed")

    # Notifications (quiet never notifies).
    if not dry_run:
        try:
            from autopilot.notify import notify
            if status in ("needs_attention", "failed", "budget_stopped") or (status == "completed" and findings):
                await notify(job, run_id, status, summary_text or None)
        except Exception:
            logger.exception("[autopilot] notify failed")

    return run, status


async def recover_running_runs() -> int:
    """Startup recovery: runs stuck 'running' from a killed process become failed
    (server_restart), matching the migration's cleanup of stale agent_tasks."""
    count = 0
    for run in await db.running_runs():
        try:
            await db.update_run(run["id"], {
                "status": "failed",
                "error_class": "server_restart",
                "error": "Server restarted while the run was in flight.",
                "finished_at": datetime.now(timezone.utc).isoformat(),
            })
            count += 1
        except Exception:
            logger.exception(f"[autopilot] recovery failed for run {run['id']}")
    if count:
        logger.info(f"[autopilot] recovered {count} run(s) stuck in 'running'")
    return count
