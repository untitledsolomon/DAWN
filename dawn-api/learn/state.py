"""Learner-state builder — a compact ≤300-token block injected into LEARN_PROMPT."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def build_learner_state(topic_id: str, max_chars: int = 1400) -> str:
    import db.client as db

    supabase = db.get_db()
    topic_res = await db._async_execute(
        lambda: supabase.table("learn_topics").select("title, level, goal").eq("id", topic_id).maybe_single().execute()
    )
    if not topic_res.data:
        return ""
    topic = topic_res.data
    parts = [f"Topic: {topic.get('title')} ({topic.get('level')})", f"Goal: {topic.get('goal') or ''}"]

    items_res = await db._async_execute(
        lambda: supabase.table("learn_items").select("front, rep_count, again_count, stability")
        .eq("topic_id", topic_id).eq("status", "active").limit(500).execute()
    )
    items = items_res.data or []
    if items:
        reps = [i.get("rep_count") or i.get("reps") or 0 for i in items]
        statuses = {"new": 0, "learning": 0, "mastered": 0}
        for i in items:
            r = i.get("rep_count") or i.get("reps") or 0
            st = i.get("stability")
            if r == 0:
                statuses["new"] += 1
            elif (st or 0) >= 21:
                statuses["mastered"] += 1
            else:
                statuses["learning"] += 1
        parts.append(f"Deck: {statuses['new']} new, {statuses['learning']} learning, {statuses['mastered']} mastered")

        weak = sorted(items, key=lambda x: -(x.get("again_count") or 0))[:5]
        if weak:
            parts.append("Weakest: " + "; ".join((i.get("front") or "")[:80] for i in weak))

    q = supabase.table("learn_attempts").select("correct").eq("topic_id", topic_id).limit(10)
    q = q.order("created_at", desc=True)
    att_res = await db._async_execute(lambda: q.execute())
    atts = att_res.data or []
    if atts:
        correct = sum(1 for a in atts if a.get("correct") is True)
        parts.append(f"Last 10 quiz: {correct}/{len(atts)}")

    text = "\n".join(parts)
    return text[:max_chars]
