"""
Alert writer — populates the `alert_events` table so the dashboard's
AlertStrip has a real source of alerts.

The dashboard was well-built but had no automatic writer anywhere — nothing
inserted into alert_events, so AlertStrip showed "nothing needs attention"
forever. This module writes alerts for real, concrete conditions:

  - pending_actions sitting unresolved past a threshold ("I have N actions
    waiting on your approval")
  - agent_tasks that ended in a failed state

These are the two most natural, judgment-safe sources to start with; more can
be added from real usage (OAuth failures, Axis health, etc.).
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import db.client as db

logger = logging.getLogger(__name__)

# A pending action older than this is "aging" and worth surfacing.
PENDING_ACTION_AGE_HOURS = 4


async def _insert_alert(severity: str, title: str, message: str, source: str, source_ref: Optional[str] = None) -> None:
    try:
        supabase = db.get_db()
        await db._async_execute(lambda: supabase.table("alert_events").insert({
            "severity": severity,
            "title": title,
            "message": message,
            "source": source,
            "source_ref": source_ref,
        }).execute())
    except Exception as e:
        logger.warning(f"[Alerts] Failed to insert alert: {e}")


async def _aging_pending_actions() -> int:
    """Insert an alert if there are pending actions unresolved past the age
    threshold. Returns the number of aging actions (0 if none)."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("pending_actions")
            .select("id, tool_name, created_at")
            .eq("status", "pending")
            .execute())
        cutoff = datetime.now(timezone.utc) - timedelta(hours=PENDING_ACTION_AGE_HOURS)
        aging = []
        for row in res.data or []:
            created = row.get("created_at")
            if not created:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
            except Exception:
                continue
            if created_dt < cutoff:
                aging.append(row)
        if aging:
            names = ", ".join(a.get("tool_name", "?") for a in aging[:5])
            await _insert_alert(
                severity="warning",
                title=f"{len(aging)} action(s) waiting on approval",
                message=f"Pending actions awaiting your approval: {names}. Review them on the Approvals page.",
                source="pending_actions",
            )
        return len(aging)
    except Exception as e:
        logger.warning(f"[Alerts] Failed to check aging pending actions: {e}")
        return 0


async def _failed_agent_tasks() -> int:
    """Insert an alert if any agent_tasks ended in a failed state recently."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("agent_tasks")
            .select("id, goal, updated_at")
            .eq("status", "failed")
            .order("updated_at", desc=True)
            .limit(10)
            .execute())
        if not res.data:
            return 0
        # Only alert on failures from the last 24h to avoid re-alerting old ones.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        recent = []
        for row in res.data or []:
            updated = row.get("updated_at")
            if not updated:
                continue
            try:
                updated_dt = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            except Exception:
                continue
            if updated_dt >= cutoff:
                recent.append(row)
        if recent:
            goal = (recent[0].get("goal") or "")[:120]
            await _insert_alert(
                severity="warning",
                title=f"{len(recent)} agent task(s) failed",
                message=f"Most recent failure: {goal}. Check the agent tasks list.",
                source="agent_tasks",
                source_ref=recent[0].get("id"),
            )
        return len(recent)
    except Exception as e:
        logger.warning(f"[Alerts] Failed to check failed agent tasks: {e}")
        return 0


async def write_alerts() -> dict:
    """Check all alert sources and write any new alert_events rows.

    Returns a summary dict. Called periodically (e.g. from the autonomous
    scheduler loop) so the dashboard stays fresh without a separate process.
    """
    aging = await _aging_pending_actions()
    failed = await _failed_agent_tasks()
    return {"aging_pending_actions": aging, "failed_agent_tasks": failed}
