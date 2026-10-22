"""Preflight checks — deterministic, no-LLM "does anything need the agent at all".

Each check returns {has_news, count, summary}. `preflight_mode='any'` records
a quiet 0-LLM run when no check has news.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def _aged_approvals(params: dict) -> dict:
    import db.client as db
    hours = int(params.get("hours") or 4)
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("pending_actions").select("id", count="exact")
        .eq("status", "pending")
        .lt("created_at", f"now() - interval '{hours} hours'")
        .execute()
    )
    count = getattr(res, "count", 0) or 0
    return {"has_news": count > 0, "count": count,
            "summary": f"{count} approval(s) pending for over {hours}h"}


async def _failed_runs(params: dict) -> dict:
    import db.client as db
    hours = int(params.get("since") or 24)
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("autopilot_runs").select("id", count="exact")
        .eq("status", "failed").gte("created_at", f"now() - interval '{hours} hours'")
        .execute()
    )
    count = getattr(res, "count", 0) or 0
    return {"has_news": count > 0, "count": count,
            "summary": f"{count} failed run(s) in the last {hours}h"}


async def _new_alerts(params: dict) -> dict:
    import db.client as db
    min_sev = params.get("min_severity") or "warning"
    order = {"info": 0, "warning": 1, "critical": 2}
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("alert_events").select("id", count="exact")
        .eq("acknowledged", False).execute()
    )
    rows = res.data or []
    if min_sev in order:
        rows = [r for r in rows if order.get(r.get("severity"), 0) >= order[min_sev]]
    count = len(rows)
    return {"has_news": count > 0, "count": count, "summary": f"{count} unacknowledged alert(s)"}


async def _events(params: dict) -> dict:
    from autopilot import db
    types = params.get("types") or []
    pending = await db.pending_events(limit=200)
    if types:
        pending = [e for e in pending if e.get("type") in types]
    return {"has_news": bool(pending), "count": len(pending),
            "summary": f"{len(pending)} pending event(s)"}


async def _learn_due(params: dict) -> dict:
    """Learning digest preflight (added with the learning spec)."""
    try:
        from routers import learn  # noqa: F401  (registered lazily)
        count = await learn.count_due()
    except Exception:
        count = 0
    min_due = int(params.get("min_due") or 1)
    return {"has_news": count >= min_due, "count": count, "summary": f"{count} cards due"}


CHECK_FUNCS = {
    "aged_approvals": _aged_approvals,
    "failed_runs": _failed_runs,
    "new_alerts": _new_alerts,
    "events": _events,
    "learn_due": _learn_due,
}


async def run_preflight(job: dict) -> list[dict]:
    """Run the job's preflight checks. Returns the news summaries; empty means
    a quiet 0-LLM run."""
    if (job.get("preflight_mode") or "any") == "off":
        return []
    checks = job.get("preflight") or []
    if not checks:
        return []
    summaries: list[dict] = []
    for ch in checks:
        if not isinstance(ch, dict):
            continue
        fn = CHECK_FUNCS.get(ch.get("check"))
        if fn is None:
            logger.warning(f"[autopilot] unknown preflight check '{ch.get('check')}'")
            continue
        try:
            result = await fn(ch.get("params") or {})
            if result and result.get("has_news"):
                summaries.append(result)
        except Exception:
            logger.exception(f"[autopilot] preflight check '{ch.get('check')}' failed")
    return summaries
