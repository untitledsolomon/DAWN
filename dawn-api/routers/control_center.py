"""
DAWN Control Center API — Dashboard aggregation endpoints for the Control Center UI.
Provides unified stats, activity logs, notifications, agent status, resources, and goals.
Queries jarvis_* tables from the Control Center's separate Supabase project.

v37.0 — Control Center Integration
v37.1 — Updated to query jarvis_* tables, added resources & goals endpoints
v37.2 — Uses separate cc_client for Control Center Supabase project
v37.3 — Fixed jarvis_resources column name (name not title), fixed notifications schema
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from config import settings
import db.cc_client as cc

logger = logging.getLogger(__name__)
router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class DashboardStats(BaseModel):
    total_tasks: int = 0
    tasks_completed: int = 0
    tasks_pending: int = 0
    tasks_in_progress: int = 0
    tasks_failed: int = 0
    active_goals: int = 0
    goal_progress_avg: float = 0
    notifications_unread: int = 0
    system_uptime: float = 99.8
    agent_status: str = "active"
    last_active: str = ""
    memory_usage: float = 42
    cpu_usage: float = 18


class WeeklyEntry(BaseModel):
    day: str
    tasks: int = 0
    posts: int = 0
    leads: int = 0


class HourlyEntry(BaseModel):
    hour: str
    value: int = 0


class ActivityEntry(BaseModel):
    id: str
    action: str
    entity_type: str
    summary: str
    severity: str
    created_at: str


class NotificationEntry(BaseModel):
    id: str
    type: str
    title: str
    description: str
    read: bool
    created_at: str
    linked_screen: Optional[str] = None


class AgentStatus(BaseModel):
    status: str = "unknown"
    uptime: float = 0
    memory_usage: float = 0
    cpu_usage: float = 0
    last_active: str = ""
    version: str = ""


class ResourceEntry(BaseModel):
    id: str
    title: str
    type: str
    url: Optional[str] = None
    description: Optional[str] = None
    created_at: str


class GoalEntry(BaseModel):
    id: str
    title: str
    category: str = ""
    target: float = 0
    current: float = 0
    unit: str = ""
    status: str = "on_track"
    due_date: Optional[str] = None


class DirectiveRequest(BaseModel):
    directive: str


class DirectiveResponse(BaseModel):
    ok: bool
    response: Optional[str] = None


class OkResponse(BaseModel):
    ok: bool


class ResourceCreate(BaseModel):
    title: str
    type: str = "document"
    url: Optional[str] = None
    description: Optional[str] = None


class GoalCreate(BaseModel):
    title: str
    category: str = "revenue"
    target: float = 0
    current: float = 0
    unit: str = ""
    status: str = "on_track"
    due_date: Optional[str] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    target: Optional[float] = None
    current: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_int(val, default=0) -> int:
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_float(val, default=0.0) -> float:
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def safe_str(val, default="") -> str:
    return str(val) if val is not None else default


# ---------------------------------------------------------------------------
# Dashboard Stats
# ---------------------------------------------------------------------------

@router.get("/dashboard/stats", response_model=DashboardStats, tags=["control-center"])
async def get_dashboard_stats(_: None = Depends(verify_key)):
    """Aggregated dashboard statistics from jarvis_* tables."""
    supabase = cc.get_cc_db()
    stats = DashboardStats()

    # Task counts from jarvis_tasks
    try:
        tasks_resp = supabase.table("jarvis_tasks").select("status").execute()
        if tasks_resp.data:
            for t in tasks_resp.data:
                s = t.get("status", "")
                stats.total_tasks += 1
                if s in ("complete", "completed", "success"):
                    stats.tasks_completed += 1
                elif s in ("queued", "pending"):
                    stats.tasks_pending += 1
                elif s in ("active", "running", "in_progress"):
                    stats.tasks_in_progress += 1
                elif s == "failed":
                    stats.tasks_failed += 1
    except Exception as e:
        logger.warning(f"[control-center] jarvis_tasks query failed: {e}")

    # Goal counts from jarvis_goals
    try:
        goals_resp = supabase.table("jarvis_goals").select("current_value,target_value").execute()
        if goals_resp.data:
            stats.active_goals = len(goals_resp.data)
            ratios = [
                g["current_value"] / g["target_value"]
                for g in goals_resp.data
                if g.get("target_value", 0) > 0
            ]
            stats.goal_progress_avg = round(sum(ratios) / len(ratios) * 100, 1) if ratios else 0
    except Exception as e:
        logger.warning(f"[control-center] jarvis_goals query failed: {e}")

    # Unread notifications from jarvis_notifications
    try:
        notif_resp = supabase.table("jarvis_notifications").select("id", count="exact").eq("is_read", False).execute()
        stats.notifications_unread = notif_resp.count or 0
    except Exception as e:
        logger.warning(f"[control-center] jarvis_notifications query failed: {e}")

    # Last activity timestamp
    try:
        activity_resp = (
            supabase.table("jarvis_activity_log")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if activity_resp.data:
            stats.last_active = safe_str(activity_resp.data[0].get("created_at", ""))
    except Exception as e:
        logger.warning(f"[control-center] jarvis_activity_log query failed: {e}")

    return stats


# ---------------------------------------------------------------------------
# Activity Log
# ---------------------------------------------------------------------------

@router.get("/activity", response_model=list[ActivityEntry], tags=["control-center"])
async def get_activity_log(limit: int = Query(20, ge=1, le=100), _: None = Depends(verify_key)):
    """Recent activity from jarvis_activity_log."""
    supabase = cc.get_cc_db()
    entries = []
    try:
        resp = (
            supabase.table("jarvis_activity_log")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        if resp.data:
            for row in resp.data:
                entries.append(ActivityEntry(
                    id=safe_str(row.get("id")),
                    action=safe_str(row.get("event_type", "sync")),
                    entity_type="task",
                    summary=safe_str(row.get("description", "")),
                    severity="info",
                    created_at=safe_str(row.get("created_at", "")),
                ))
    except Exception as e:
        logger.warning(f"[control-center] activity log failed: {e}")
    return entries


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=list[NotificationEntry], tags=["control-center"])
async def get_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread: Optional[bool] = None,
    _: None = Depends(verify_key),
):
    """Get notifications from jarvis_notifications."""
    supabase = cc.get_cc_db()
    entries = []
    try:
        query = (
            supabase.table("jarvis_notifications")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if unread is True:
            query = query.eq("is_read", False)
        elif unread is False:
            query = query.eq("is_read", True)

        resp = query.execute()
        if resp.data:
            for row in resp.data:
                entries.append(NotificationEntry(
                    id=safe_str(row.get("id")),
                    type=safe_str(row.get("type", "update")),
                    title=safe_str(row.get("title", "")),
                    description=safe_str(row.get("description", "")),
                    read=bool(row.get("is_read", False)),
                    created_at=safe_str(row.get("created_at", "")),
                    linked_screen=row.get("linked_screen"),
                ))
    except Exception as e:
        logger.warning(f"[control-center] notifications query failed: {e}")
    return entries


@router.post("/notifications/{notification_id}/read", response_model=OkResponse, tags=["control-center"])
async def mark_notification_read(notification_id: str, _: None = Depends(verify_key)):
    """Mark a notification as read in jarvis_notifications."""
    supabase = cc.get_cc_db()
    try:
        supabase.table("jarvis_notifications").update({"is_read": True}).eq("id", notification_id).execute()
        return OkResponse(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Weekly / Hourly Activity (for charts)
# ---------------------------------------------------------------------------

@router.get("/dashboard/activity/weekly", response_model=list[WeeklyEntry], tags=["control-center"])
async def get_weekly_activity(_: None = Depends(verify_key)):
    """7-day activity aggregated by day from jarvis_activity_log."""
    supabase = cc.get_cc_db()
    today = datetime.utcnow()
    days = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        day_label = day.strftime("%a")
        days.append((day_str, day_label))

    entries = []
    try:
        for day_str, day_label in days:
            resp = (
                supabase.table("jarvis_activity_log")
                .select("event_type")
                .gte("created_at", day_str)
                .lt("created_at", (datetime.strptime(day_str, "%Y-%m-%d") + timedelta(days=1)).isoformat())
                .execute()
            )

            tasks = 0
            posts = 0
            leads = 0
            if resp.data:
                for row in resp.data:
                    et = row.get("event_type", "")
                    if et in ("task_complete", "task_started"):
                        tasks += 1
                    elif et == "content_posted":
                        posts += 1
                    elif et in ("lead_scraped", "outreach_sent"):
                        leads += 1
                    else:
                        tasks += 1

            entries.append(WeeklyEntry(day=day_label, tasks=tasks, posts=posts, leads=leads))
    except Exception as e:
        logger.warning(f"[control-center] weekly activity failed: {e}")

    return entries


@router.get("/dashboard/activity/hourly", response_model=list[HourlyEntry], tags=["control-center"])
async def get_hourly_activity(_: None = Depends(verify_key)):
    """24-hour activity distribution from jarvis_activity_log."""
    supabase = cc.get_cc_db()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    hours = [f"{h:02d}" for h in range(6, 22)]  # 06:00 to 21:00

    entries = []
    try:
        for hour in hours:
            start = f"{today}T{hour}:00:00"
            end_h = int(hour) + 1
            end = f"{today}T{end_h:02d}:00:00"

            resp = (
                supabase.table("jarvis_activity_log")
                .select("id", count="exact")
                .gte("created_at", start)
                .lt("created_at", end)
                .execute()
            )

            entries.append(HourlyEntry(hour=hour, value=resp.count or 0))
    except Exception as e:
        logger.warning(f"[control-center] hourly activity failed: {e}")

    return entries


# ---------------------------------------------------------------------------
# Agent Status
# ---------------------------------------------------------------------------

@router.get("/agent/status", response_model=AgentStatus, tags=["control-center"])
async def get_agent_status(_: None = Depends(verify_key)):
    """Get DAWN agent status."""
    supabase = cc.get_cc_db()
    status = AgentStatus(status="active", version=settings.llm_mode)

    try:
        activity_resp = (
            supabase.table("jarvis_activity_log")
            .select("created_at")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if activity_resp.data:
            status.last_active = safe_str(activity_resp.data[0].get("created_at", ""))
    except Exception:
        pass

    return status


@router.post("/agent/directive", response_model=DirectiveResponse, tags=["control-center"])
async def send_directive(req: DirectiveRequest, _: None = Depends(verify_key)):
    """Send a directive to the DAWN agent."""
    try:
        from llm.engine import get_engine
        engine = get_engine()
        response = await engine.complete([
            {"role": "system", "content": "You are DAWN, the Digital AI Working Network. Execute the following directive."},
            {"role": "user", "content": req.directive},
        ])
        return DirectiveResponse(ok=True, response=response)
    except Exception as e:
        logger.error(f"[control-center] directive failed: {e}")
        return DirectiveResponse(ok=False, response=f"Error: {str(e)}")


# ---------------------------------------------------------------------------
# Resources (jarvis_resources) — NOTE: column is 'name' not 'title'
# ---------------------------------------------------------------------------

@router.get("/resources", response_model=list[ResourceEntry], tags=["control-center"])
async def get_resources(limit: int = Query(50, ge=1, le=200), _: None = Depends(verify_key)):
    """List resources from jarvis_resources. Uses 'name' column as title."""
    supabase = cc.get_cc_db()
    entries = []
    try:
        resp = (
            supabase.table("jarvis_resources")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        if resp.data:
            for row in resp.data:
                entries.append(ResourceEntry(
                    id=safe_str(row.get("id")),
                    title=safe_str(row.get("name", "")),  # column is 'name' not 'title'
                    type=safe_str(row.get("type", "document")),
                    url=row.get("file_url"),  # column is 'file_url' not 'url'
                    description=safe_str(row.get("category", "")),  # use category as description
                    created_at=safe_str(row.get("created_at", "")),
                ))
    except Exception as e:
        logger.warning(f"[control-center] resources query failed: {e}")
    return entries


@router.post("/resources", response_model=ResourceEntry, tags=["control-center"])
async def create_resource(resource: ResourceCreate, _: None = Depends(verify_key)):
    """Create a resource in jarvis_resources. Uses 'name' column."""
    supabase = cc.get_cc_db()
    try:
        resp = (
            supabase.table("jarvis_resources")
            .insert({
                "name": resource.title,  # column is 'name' not 'title'
                "type": resource.type,
                "file_url": resource.url,  # column is 'file_url' not 'url'
                "category": resource.description or "general",
            })
            .execute()
        )
        if resp.data and len(resp.data) > 0:
            row = resp.data[0]
            return ResourceEntry(
                id=safe_str(row.get("id")),
                title=safe_str(row.get("name", "")),
                type=safe_str(row.get("type", "document")),
                url=row.get("file_url"),
                description=safe_str(row.get("category", "")),
                created_at=safe_str(row.get("created_at", "")),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Failed to create resource")


# ---------------------------------------------------------------------------
# Goals (jarvis_goals)
# ---------------------------------------------------------------------------

@router.get("/goals", response_model=list[GoalEntry], tags=["control-center"])
async def get_goals(limit: int = Query(50, ge=1, le=200), _: None = Depends(verify_key)):
    """List goals from jarvis_goals."""
    supabase = cc.get_cc_db()
    entries = []
    try:
        resp = (
            supabase.table("jarvis_goals")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        if resp.data:
            for row in resp.data:
                entries.append(GoalEntry(
                    id=safe_str(row.get("id")),
                    title=safe_str(row.get("title", "")),
                    category=safe_str(row.get("category", "")),
                    target=safe_float(row.get("target_value", 0)),
                    current=safe_float(row.get("current_value", 0)),
                    unit=safe_str(row.get("unit", "")),
                    status=safe_str(row.get("status", "on_track")),
                    due_date=row.get("due_date"),
                ))
    except Exception as e:
        logger.warning(f"[control-center] goals query failed: {e}")
    return entries


@router.post("/goals", response_model=GoalEntry, tags=["control-center"])
async def create_goal(goal: GoalCreate, _: None = Depends(verify_key)):
    """Create a goal in jarvis_goals."""
    supabase = cc.get_cc_db()
    try:
        resp = (
            supabase.table("jarvis_goals")
            .insert({
                "title": goal.title,
                "category": goal.category,
                "target_value": goal.target,
                "current_value": goal.current,
                "unit": goal.unit,
                "status": goal.status,
                "due_date": goal.due_date,
            })
            .execute()
        )
        if resp.data and len(resp.data) > 0:
            row = resp.data[0]
            return GoalEntry(
                id=safe_str(row.get("id")),
                title=safe_str(row.get("title", "")),
                category=safe_str(row.get("category", "")),
                target=safe_float(row.get("target_value", 0)),
                current=safe_float(row.get("current_value", 0)),
                unit=safe_str(row.get("unit", "")),
                status=safe_str(row.get("status", "on_track")),
                due_date=row.get("due_date"),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Failed to create goal")


@router.put("/goals/{goal_id}", response_model=GoalEntry, tags=["control-center"])
async def update_goal(goal_id: str, goal: GoalUpdate, _: None = Depends(verify_key)):
    """Update a goal in jarvis_goals."""
    supabase = cc.get_cc_db()
    updates = {}
    if goal.title is not None:
        updates["title"] = goal.title
    if goal.category is not None:
        updates["category"] = goal.category
    if goal.target is not None:
        updates["target_value"] = goal.target
    if goal.current is not None:
        updates["current_value"] = goal.current
    if goal.unit is not None:
        updates["unit"] = goal.unit
    if goal.status is not None:
        updates["status"] = goal.status
    if goal.due_date is not None:
        updates["due_date"] = goal.due_date

    try:
        resp = (
            supabase.table("jarvis_goals")
            .update(updates)
            .eq("id", goal_id)
            .execute()
        )
        if resp.data and len(resp.data) > 0:
            row = resp.data[0]
            return GoalEntry(
                id=safe_str(row.get("id")),
                title=safe_str(row.get("title", "")),
                category=safe_str(row.get("category", "")),
                target=safe_float(row.get("target_value", 0)),
                current=safe_float(row.get("current_value", 0)),
                unit=safe_str(row.get("unit", "")),
                status=safe_str(row.get("status", "on_track")),
                due_date=row.get("due_date"),
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=500, detail="Goal not found")


@router.delete("/goals/{goal_id}", response_model=OkResponse, tags=["control-center"])
async def delete_goal(goal_id: str, _: None = Depends(verify_key)):
    """Delete a goal from jarvis_goals."""
    supabase = cc.get_cc_db()
    try:
        supabase.table("jarvis_goals").delete().eq("id", goal_id).execute()
        return OkResponse(ok=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
