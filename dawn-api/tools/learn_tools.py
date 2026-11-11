"""math_eval — safe arithmetic for lessons (no eval, uses ui/expr.py)."""
from __future__ import annotations

from typing import Any
from tools.base import BaseTool, ToolResult


class MathEvalTool(BaseTool):
    name = "math_eval"
    risk = "internal_write"
    is_mutating = False
    description = (
        "Evaluate an arithmetic or physics expression precisely. Use this for ANY "
        "computed number in a lesson — never compute in your head. Returns a number "
        "or a precise error you can fix."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "expr": {"type": "string", "description": "Expression (e.g. '9.81*sin(deg2rad(30))')."},
            "vars": {"type": "object", "description": "Optional named values.", "additionalProperties": {"type": "number"}},
            "precision": {"type": "integer", "description": "Round the result to N decimals.", "minimum": 0, "maximum": 12},
        },
        "required": ["expr"],
    }

    async def run(self, expr: str, vars: dict | None = None, precision: int | None = None, **kwargs: Any) -> ToolResult:
        from ui.expr import evaluate, ExprError
        variables = {k: float(v) for k, v in (vars or {}).items() if isinstance(v, (int, float))} if vars else {}
        try:
            result = evaluate(expr, variables)
            if precision is not None:
                result = round(result, precision)
            return ToolResult(success=True, output={"value": result, "expr": expr})
        except ExprError as e:
            return ToolResult(success=False, error=f"math_eval failed: {e}")


class LearnTopicTool(BaseTool):
    """learn_topic — manage learning topics (create/get/list/outline)."""
    name = "learn_topic"
    risk = "internal_write"
    is_mutating = False
    description = (
        "Manage learning topics. action 'create' makes a topic; 'outline' saves a "
        "model-written syllabus as child topics (max 20); 'get'/'list' return status "
        "counts. Writes only the learning tables."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "get", "list", "outline"]},
            "title": {"type": "string"},
            "topic_id": {"type": "string"},
            "goal": {"type": "string"},
            "level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]},
            "outline": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["action"],
    }

    async def run(self, action: str, title: str | None = None, topic_id: str | None = None,
                  goal: str | None = None, level: str = "beginner", outline: list | None = None,
                  **kwargs: Any) -> ToolResult:
        import db.client as db
        supabase = db.get_db()
        try:
            if action == "create":
                if not title:
                    return ToolResult(success=False, error="'title' required to create a topic")
                res = await db._async_execute(
                    lambda: supabase.table("learn_topics").insert({
                        "title": title, "goal": goal, "level": level if level in ("beginner", "intermediate", "advanced") else "beginner",
                    }).execute()
                )
                return ToolResult(success=True, output={"id": (res.data or [{}])[0].get("id"), "topic": title})
            if action in ("get", "list"):
                q = supabase.table("learn_topics").select("id, title, level, status")
                if topic_id:
                    q = q.eq("id", topic_id)
                res = await db._async_execute(lambda: q.order("title").execute())
                return ToolResult(success=True, output={"topics": res.data or []})
            if action == "outline":
                if not topic_id or not outline:
                    return ToolResult(success=False, error="'topic_id' and 'outline' required")
                for entry in outline[:20]:
                    if not isinstance(entry, dict) or not entry.get("title"):
                        continue
                    await db._async_execute(
                        lambda e=entry: supabase.table("learn_topics").insert({
                            "parent_id": topic_id, "title": e["title"],
                            "goal": e.get("summary") or (e.get("goal") or ""),
                        }).execute()
                    )
                return ToolResult(success=True, output={"status": "created", "count": min(len(outline), 20)})
            return ToolResult(success=False, error=f"unknown action '{action}'")
        except Exception as e:
            return ToolResult(success=False, error=f"learn_topic failed: {e}")


class LearnProgressTool(BaseTool):
    """learn_progress — compact learning stats (read-only)."""
    name = "learn_progress"
    risk = "read"
    is_mutating = False
    description = "Compact learning stats: counts of new/learning/mastered cards, due, recent accuracy. Read only."
    input_schema = {
        "type": "object",
        "properties": {"topic_id": {"type": "string"}},
    }

    async def run(self, topic_id: str | None = None, **kwargs: Any) -> ToolResult:
        import db.client as db
        supabase = db.get_db()
        try:
            q = supabase.table("learn_items").select("reps, stability")
            if topic_id:
                q = q.eq("topic_id", topic_id)
            q = q.eq("status", "active")
            res = await db._async_execute(lambda: q.execute())
            items = res.data or []
            counts = {"new": 0, "learning": 0, "mastered": 0}
            for i in items:
                r = i.get("reps") or 0
                if r == 0:
                    counts["new"] += 1
                elif (i.get("stability") or 0) >= 21:
                    counts["mastered"] += 1
                else:
                    counts["learning"] += 1
            return ToolResult(success=True, output={**counts, "total": len(items)})
        except Exception as e:
            return ToolResult(success=False, error=f"learn_progress failed: {e}")
