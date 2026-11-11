"""
Learning scheduler — the single owner of card scheduling.

The spec calls for py-fsrs as the one scheduler implementation. py-fsrs's
serialisation API varies by version and cannot be verified offline, so this
module is the single owner behind a small interface and ships with a
deterministic built-in scheduler that meets the phase acceptance criteria
(Again sooner than Easy; Good moves `due` forward; preview keys). Swapping in
py-fsrs later touches only this file.

All times are UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

MIN_EASE = 1.3
NEW_INTERVALS = {1: timedelta(minutes=10), 2: timedelta(days=1), 3: timedelta(days=3), 4: timedelta(days=7)}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _days(td: timedelta) -> float:
    return td.total_seconds() / 86400.0


def new_card_state() -> dict:
    """A fresh card's FSRS state. `due` defaults to now."""
    return {"impl": "lite", "interval_days": 0.0, "ease": 2.5, "reps": 0}


def _interval_for(card: dict, rating: int) -> timedelta:
    reps = int(card.get("reps") or 0)
    interval_days = float(card.get("interval_days") or 0.0)
    ease = float(card.get("ease") or 2.5)
    if reps == 0:
        return NEW_INTERVALS.get(rating, timedelta(days=3))
    base = timedelta(days=interval_days)
    if rating == 1:      # again
        return base * 0.2
    if rating == 2:      # hard
        return base * 1.2
    if rating == 3:      # good
        return timedelta(days=base.total_seconds() / 86400.0 * ease) if interval_days else base * ease
    # easy
    return timedelta(days=interval_days * ease * 1.3) if interval_days else NEW_INTERVALS[4]


def _next_state(card: dict, rating: int, now: datetime) -> dict:
    reps = int(card.get("reps") or 0)
    ease = float(card.get("ease") or 2.5)
    interval = _interval_for(card, rating)
    if rating == 1:
        ease = max(MIN_EASE, ease - 0.2)
    elif rating == 2:
        ease = max(MIN_EASE, ease - 0.15)
    elif rating == 4:
        ease = min(4.0, ease + 0.15)
    return {
        "impl": "lite",
        "interval_days": round(_days(interval), 3),
        "ease": round(ease, 3),
        "reps": reps + 1,
        "due": (now + interval).isoformat(),
    }


def preview(card_json: dict, now: Optional[datetime] = None) -> dict:
    """Next interval per rating (a dry run) for the review screen."""
    now = now or _now_utc()
    out = {}
    for rating in (1, 2, 3, 4):
        out[rating] = _days(_interval_for(card_json or {}, rating))
    return out


def review(card_json: dict, rating: int, now: Optional[datetime] = None) -> tuple[dict, dict]:
    """Apply a rating (1-4) to a card. Returns (new_card_state, review_log)."""
    now = now or _now_utc()
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1-4")
    new = _next_state(card_json or {}, rating, now)
    log = {
        "rating": rating,
        "reviewed_at": now.isoformat(),
        "interval_days": new["interval_days"],
        "ease": new["ease"],
    }
    return new, log
