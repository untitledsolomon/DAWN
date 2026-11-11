"""Learning mode API — topics, review queue, cards, attempts, stats."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from config import settings as app_settings
from runtime_settings import get_runtime
from learn import scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# Single alias so an in-app login can swap the auth dependency in one place.
require_auth = verify_key

import db.client as db  # noqa: E402


# ── day rollover ─────────────────────────────────────────────────────────────
def _day_start() -> datetime:
    rt = get_runtime()
    tz = ZoneInfo(rt.get("app.timezone") or "Africa/Kampala")
    rollover = int(rt.get("learn.day_rollover_hour") or 4)
    local_now = datetime.now(tz)
    start = local_now.replace(hour=rollover, minute=0, second=0, microsecond=0)
    if local_now < start:
        start = start.replace(day=local_now.day - 1)
    return start


async def count_due() -> int:
    """Due-card count used by the learn_due preflight check."""
    try:
        res = await db._async_execute(
            lambda: db.get_db().table("learn_items").select("id", count="exact")
            .eq("status", "active").lte("due", "now()").execute()
        )
        return getattr(res, "count", 0) or 0
    except Exception:
        return 0


# ── topics ───────────────────────────────────────────────────────────────────
class TopicCreate(BaseModel):
    title: str
    parent_id: Optional[str] = None
    goal: Optional[str] = None
    level: str = "beginner"


class TopicPatch(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    goal: Optional[str] = None
    level: Optional[str] = None
    status: Optional[str] = None
    prerequisite_ids: Optional[list[str]] = None


@router.get("/learn/topics", tags=["learn"])
async def list_topics(_: None = Depends(require_auth)):
    res = await db._async_execute(lambda: db.get_db().table("learn_topics").select("*").order("title").execute())
    return res.data or []


@router.post("/learn/topics", tags=["learn"])
async def create_topic(req: TopicCreate, _: None = Depends(require_auth)):
    data = req.model_dump()
    if data.get("level") not in ("beginner", "intermediate", "advanced"):
        data["level"] = "beginner"
    res = await db._async_execute(lambda: db.get_db().table("learn_topics").insert(data).execute())
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create topic")
    return res.data[0]


@router.get("/learn/topics/{topic_id}", tags=["learn"])
async def get_topic(topic_id: str, _: None = Depends(require_auth)):
    res = await db._async_execute(
        lambda: db.get_db().table("learn_topics").select("*").eq("id", topic_id).maybe_single().execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Topic not found")
    return res.data


@router.patch("/learn/topics/{topic_id}", tags=["learn"])
async def patch_topic(topic_id: str, req: TopicPatch, _: None = Depends(require_auth)):
    data = {k: v for k, v in req.model_dump().items() if v is not None}
    data["updated_at"] = "now()"
    res = await db._async_execute(lambda: db.get_db().table("learn_topics").update(data).eq("id", topic_id).execute())
    return (res.data or [{}])[0]


@router.get("/learn/topics/{topic_id}/lessons", tags=["learn"])
async def topic_lessons(topic_id: str, _: None = Depends(require_auth)):
    res = await db._async_execute(
        lambda: db.get_db().table("learn_lessons").select("*").eq("topic_id", topic_id).order("created_at", desc=True).execute()
    )
    return res.data or []


@router.get("/learn/lessons/{artifact_id}", tags=["learn"])
async def lesson_by_artifact(artifact_id: str, _: None = Depends(require_auth)):
    res = await db._async_execute(
        lambda: db.get_db().table("learn_lessons").select("*").eq("artifact_id", artifact_id).maybe_single().execute()
    )
    return res.data


# ── queue ────────────────────────────────────────────────────────────────────
@router.get("/learn/queue", tags=["learn"])
async def review_queue(topic_id: Optional[str] = None, limit: int = Query(50, le=200), _: None = Depends(require_auth)):
    rt = get_runtime()
    day = _day_start()
    supabase = db.get_db()
    reviewed = await db._async_execute(
        lambda: supabase.table("learn_reviews").select("item_id").gte("reviewed_at", day.isoformat()).execute()
    )
    reviewed_ids = {r["item_id"] for r in reviewed.data or []}

    q = supabase.table("learn_items").select("*").eq("status", "active").lte("due", "now()").order("due").limit(limit + 100)
    res = await db._async_execute(lambda: q.execute())
    items = res.data or []

    new_cap = int(rt.get("learn.new_cards_per_day") or 10)
    review_cap = int(rt.get("learn.max_reviews_per_day") or 150)
    new_shown = 0
    queue = []
    for item in items:
        reps = item.get("reps") or 0
        if reps == 0:
            if new_shown >= new_cap:
                continue
            new_shown += 1
        else:
            if len(queue) >= review_cap:
                break
        item["_preview"] = scheduler.preview(item.get("fsrs") or {}, datetime.now(timezone.utc))
        queue.append(item)
        if len(queue) >= limit:
            break

    return {
        "items": queue,
        "due": len(items),
        "new_remaining": max(0, new_cap - new_shown),
        "reviewed_today": len(reviewed_ids),
    }


# ── review ───────────────────────────────────────────────────────────────────
class ReviewBody(BaseModel):
    item_id: str
    rating: int
    client_review_id: Optional[str] = None
    duration_ms: Optional[int] = None


def _serialize_card(state: dict) -> dict:
    return {k: v for k, v in state.items() if k != "due"}


@router.post("/learn/review", tags=["learn"])
async def review_item(req: ReviewBody, _: None = Depends(require_auth)):
    supabase = db.get_db()
    if req.rating not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="rating must be 1-4")

    # Idempotent: a repeated client_review_id returns the stored result.
    if req.client_review_id:
        existing = await db._async_execute(
            lambda: supabase.table("learn_reviews").select("*").eq("client_review_id", req.client_review_id).maybe_single().execute()
        )
        if existing.data:
            return {"status": "already_recorded", "review": existing.data}

    item_res = await db._async_execute(
        lambda: supabase.table("learn_items").select("*").eq("id", req.item_id).maybe_single().execute()
    )
    item = item_res.data
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    now = datetime.now(timezone.utc)
    new_state, log = scheduler.review(item.get("fsrs") or {}, req.rating, now)

    row = {
        "fsrs": json.dumps(new_state),
        "due": new_state.get("due"),
        "stability": new_state.get("interval_days"),
        "reps": new_state.get("reps"),
        "again_count": (item.get("again_count") or 0) + (1 if req.rating == 1 else 0),
        "last_reviewed_at": now.isoformat(),
        "updated_at": "now()",
    }
    await db._async_execute(lambda: supabase.table("learn_items").update(row).eq("id", req.item_id).execute())

    review_row = {
        "client_review_id": req.client_review_id,
        "item_id": req.item_id,
        "rating": req.rating,
        "duration_ms": req.duration_ms,
        "log": json.dumps(log),
    }
    rev_res = await db._async_execute(lambda: supabase.table("learn_reviews").insert(review_row).execute())
    return {"status": "recorded", "next_due": new_state.get("due"), "intervals": scheduler.preview(new_state, now)}


# ── items ────────────────────────────────────────────────────────────────────
class ItemCreate(BaseModel):
    topic_id: str
    items: list[dict]


@router.post("/learn/items", tags=["learn"])
async def create_items(req: ItemCreate, _: None = Depends(require_auth)):
    supabase = db.get_db()
    created = []
    duplicates = []
    for it in req.items:
        front = (it.get("front") or "").strip()
        back = (it.get("back") or "").strip()
        if not front or not back:
            continue
        dupe = await db._async_execute(
            lambda: supabase.table("learn_items").select("id")
            .eq("topic_id", req.topic_id).ilike("front", front).maybe_single().execute()
        )
        if dupe.data:
            duplicates.append({"front": front, "id": dupe.data["id"]})
            continue
        state = scheduler.new_card_state()
        state["due"] = datetime.now(timezone.utc).isoformat()
        res = await db._async_execute(
            lambda: supabase.table("learn_items").insert({
                "topic_id": req.topic_id,
                "front": front,
                "back": back,
                "tags": it.get("tags") or [],
                "source_ref": it.get("source_ref"),
                "fsrs": json.dumps(state),
                "stability": 0.0,
            }).execute()
        )
        if res.data:
            created.append({"id": res.data[0]["id"], "front": front})
    return {"created": created, "duplicates": duplicates}


@router.patch("/learn/items/{item_id}", tags=["learn"])
async def patch_item(item_id: str, body: dict, _: None = Depends(require_auth)):
    data = {k: v for k, v in body.items() if v is not None and k in ("front", "back", "tags", "status")}
    data["updated_at"] = "now()"
    await db._async_execute(lambda: db.get_db().table("learn_items").update(data).eq("id", item_id).execute())
    return {"status": "updated"}


@router.delete("/learn/items/{item_id}", tags=["learn"])
async def delete_item(item_id: str, _: None = Depends(require_auth)):
    await db._async_execute(lambda: db.get_db().table("learn_items").delete().eq("id", item_id).execute())
    return {"status": "deleted"}


# ── attempts (quiz results) ──────────────────────────────────────────────────
class Attempt(BaseModel):
    topic_id: Optional[str] = None
    artifact_id: Optional[str] = None
    block_id: Optional[str] = None
    question_id: Optional[str] = None
    kind: str = "mcq"
    correct: Optional[bool] = None
    self_rating: Optional[str] = None
    hints_used: int = 0


@router.post("/learn/attempts", tags=["learn"])
async def record_attempts(attempts: list[Attempt], _: None = Depends(require_auth)):
    supabase = db.get_db()
    rows = []
    for a in attempts:
        row = a.model_dump()
        if row.get("kind") not in ("mcq", "short"):
            row["kind"] = "mcq"
        if row.get("self_rating") not in (None, "missed", "partly", "got_it"):
            row["self_rating"] = None
        rows.append(row)
    if rows:
        await db._async_execute(lambda: supabase.table("learn_attempts").insert(rows).execute())
    return {"status": "recorded", "count": len(rows)}


# ── stats ────────────────────────────────────────────────────────────────────
@router.get("/learn/stats", tags=["learn"])
async def learn_stats(topic_id: Optional[str] = None, _: None = Depends(require_auth)):
    supabase = db.get_db()
    items_res = await db._async_execute(
        lambda: supabase.table("learn_items").select("id, reps, stability, again_count")
        .eq("topic_id", topic_id).eq("status", "active").execute()
    ) if topic_id else await db._async_execute(
        lambda: supabase.table("learn_items").select("id, reps, stability, again_count").eq("status", "active").execute()
    )
    items = items_res.data or []
    counts = {"new": 0, "learning": 0, "mastered": 0, "due": 0}
    for i in items:
        r = i.get("reps") or 0
        st = i.get("stability") or 0
        if r == 0:
            counts["new"] += 1
        elif st >= 21:
            counts["mastered"] += 1
        else:
            counts["learning"] += 1
    due_res = await db._async_execute(
        lambda: supabase.table("learn_items").select("id", count="exact")
        .eq("status", "active").lte("due", "now()").execute()
    )
    counts["due"] = getattr(due_res, "count", 0) or 0
    return {"totals": counts, "due": counts["due"], "by_topic": len(items)}
