"""
Main chat endpoint — streaming LLM response with knowledge graph context.
Now persists messages to the database, generates AI titles, extracts memory,
and learns from errors.
"""
import json
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from config import settings
from llm.engine import get_engine, build_messages
from llm.tools import build_context, extract_memory_facts, extract_error_pattern, extract_key_terms
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: Optional[str] = None


# ── SSE helpers ───────────────────────────────────────────────────────

def sse(event_type: str, payload) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ── DB helpers ────────────────────────────────────────────────────────

def _save_message_sync(session_id: str, role: str, content: str,
                       tool_calls: Optional[list] = None,
                       node_ids: Optional[list[str]] = None,
                       node_titles: Optional[list[str]] = None) -> dict:
    """Insert a message into chat_messages (sync — called from async generator)."""
    try:
        supabase = db.get_db()
        data = {
            "session_id": session_id,
            "role": role,
            "content": content,
        }
        if tool_calls:
            data["tool_calls"] = tool_calls  # Pass list directly, not json.dumps — JSONB handles it
        if node_ids:
            data["node_ids"] = node_ids
        if node_titles:
            data["node_titles"] = node_titles
        res = supabase.table("chat_messages").insert(data).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[chat] Failed to save message: {e}")
        return {}


def _ensure_session_sync(session_id: Optional[str]) -> str:
    """Return a valid session_id, creating one if needed (sync)."""
    try:
        supabase = db.get_db()
        if session_id:
            res = supabase.table("chat_sessions").select("id").eq("id", session_id).execute()
            if res.data:
                return session_id
        res = supabase.table("chat_sessions").insert({"title": "New Chat"}).execute()
        return res.data[0]["id"] if res.data else "unknown"
    except Exception as e:
        logger.error(f"[chat] Failed to ensure session: {e}")
        return session_id or "unknown"


def _needs_title_sync(session_id: str) -> bool:
    """Whether a session still has its placeholder title and should be
    (re)titled from the first real message. Checking DB state — rather than
    just "was session_id absent from the request" — means sessions that got
    stuck as "New Chat" (e.g. from an earlier bug, or a client retry) get
    fixed automatically on their next message instead of staying broken
    forever."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_sessions").select("title").eq("id", session_id).execute()
        if not res.data:
            return True
        title = (res.data[0].get("title") or "").strip()
        return title == "" or title == "New Chat"
    except Exception as e:
        logger.warning(f"[chat] Failed to check session title: {e}")
        return False


async def _generate_title(session_id: str, first_message: str, llm_complete_fn):
    """Generate a concise, meaningful title using the LLM."""
    prompt = (
        "Generate a very short title (max 6 words) for this conversation starter. "
        "Return ONLY the title, no quotes, no punctuation.\n\n"
        f"Message: {first_message[:500]}"
    )
    try:
        title = await llm_complete_fn([{"role": "user", "content": prompt}])
        title = title.strip().strip('"').strip("'").strip()
        if len(title) > 60:
            title = title[:60]
        if len(title) < 3:
            title = first_message[:60].strip()
    except Exception as e:
        logger.warning(f"[chat] Title generation failed: {e}")
        title = first_message[:60].strip()

    if len(title) < 3:
        title = "New Chat"

    try:
        supabase = db.get_db()
        supabase.table("chat_sessions").update({"title": title}).eq("id", session_id).execute()
    except Exception as e:
        logger.warning(f"[chat] Failed to save title: {e}")


async def _load_memory_context(query: str) -> str:
    """Load relevant memory nodes from the knowledge graph for context."""
    try:
        terms = extract_key_terms(query)
        memory_parts = []
        seen = set()

        for term in terms[:3]:
            results = await db.rpc_fuzzy_search(term, limit=3, threshold=0.2)
            for node in results:
                if node.get("id") not in seen and node.get("type") in ("memory", "fact", "preference"):
                    seen.add(node["id"])
                    if node.get("body"):
                        memory_parts.append(f"[{node['type']}] {node['title']}: {node['body']}")

        if memory_parts:
            return "Relevant memories:\n" + "\n".join(memory_parts[:5])
        return ""
    except Exception as e:
        logger.warning(f"[chat] Memory context load failed: {e}")
        return ""


async def _extract_and_store_memory(
    user_message: str,
    assistant_response: str,
    session_id: str,
    llm_complete_fn,
):
    """Extract durable facts from conversation and store as memory nodes."""
    try:
        conversation = f"User: {user_message}\nDAWN: {assistant_response}"
        facts = await extract_memory_facts(conversation, llm_complete_fn)

        if not facts:
            return

        supabase = db.get_db()

        # Create memory session
        session_res = supabase.table("memory_sessions").insert({
            "session_source": "dawn_web",
            "summary": user_message[:100],
        }).execute()
        session = session_res.data[0] if session_res.data else {}

        for fact in facts[:5]:
            node_res = supabase.table("nodes").insert({
                "title": fact.get("title", "Memory fact"),
                "type": "memory",
                "body": fact.get("body", ""),
                "status": "draft",
                "source": "conversation",
                "source_ref": session_id,
                "confidence": fact.get("confidence", 0.7),
            }).execute()
            node = node_res.data[0] if node_res.data else {}

            if node.get("id") and session.get("id"):
                supabase.table("memory_node_origins").insert({
                    "node_id": node["id"],
                    "session_id": session["id"],
                }).execute()

                # Log the extraction
                try:
                    supabase.table("knowledge_extractions").insert({
                        "session_id": session_id,
                        "node_id": node["id"],
                        "extraction_type": fact.get("type", "memory"),
                        "confidence": fact.get("confidence", 0.7),
                    }).execute()
                except Exception:
                    pass

            # Attach tags
            for tag_name in fact.get("tags", []):
                try:
                    all_tags_res = supabase.table("tags").select("*").execute()
                    all_tags = all_tags_res.data or []
                    tag = next((t for t in all_tags if t["name"] == tag_name), None)
                    if tag:
                        supabase.table("node_tags").upsert({
                            "node_id": node["id"],
                            "tag_id": tag["id"],
                        }).execute()
                except Exception:
                    pass
    except Exception as e:
        logger.warning(f"[chat] Memory extraction failed: {e}")


async def _learn_from_error(
    user_message: str,
    assistant_response: str,
    llm_complete_fn,
):
    """Extract error patterns from conversations where DAWN made mistakes."""
    try:
        pattern = await extract_error_pattern(user_message, assistant_response, llm_complete_fn)
        if not pattern:
            return

        supabase = db.get_db()
        existing = supabase.table("error_patterns").select("id, frequency").eq(
            "pattern", pattern["pattern"]
        ).execute()
        if existing.data:
            supabase.table("error_patterns").update({
                "frequency": existing.data[0]["frequency"] + 1,
                "last_seen": "now()",
                "resolution": pattern.get("resolution", existing.data[0].get("resolution", "")),
            }).eq("id", existing.data[0]["id"]).execute()
        else:
            supabase.table("error_patterns").insert({
                "pattern": pattern["pattern"],
                "context": pattern.get("context", ""),
                "resolution": pattern.get("resolution", ""),
                "frequency": 1,
            }).execute()
    except Exception as e:
        logger.warning(f"[chat] Error learning failed: {e}")


# ── Main chat endpoint ────────────────────────────────────────────────

@router.post("/")
async def chat(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    engine = get_engine()
    full_response = []
    tool_calls_list: list[dict] = []
    final_node_ids: list[str] = []
    final_node_titles: list[str] = []

    # Ensure we have a session (sync call is fine here)
    session_id = _ensure_session_sync(req.session_id)

    async def generate():
        nonlocal full_response, tool_calls_list, final_node_ids, final_node_titles

        # 1. Save user message immediately
        _save_message_sync(session_id, "user", req.message)

        # 2. Auto-title on first message (using AI) — retitle whenever the
        # session still has its placeholder title, not just when the request
        # omitted session_id, so previously-stuck "New Chat" sessions self-heal.
        if _needs_title_sync(session_id):
            background_tasks.add_task(_generate_title, session_id, req.message, engine.complete)

        # 3. Show thinking state
        yield sse("thinking", {"content": "Searching knowledge graph..."})
        await asyncio.sleep(0)

        # 4. Load memory context (personal facts, preferences, past learnings)
        memory_context = await _load_memory_context(req.message)

        # 5. Build context from graph
        context_result = await build_context(req.message)

        # 6. Stream tool call events to frontend
        for tc in context_result.tool_calls:
            tc_dict = {"name": tc.name, "args": tc.args, "result_count": tc.result_count}
            tool_calls_list.append(tc_dict)
            yield sse("tool", tc_dict)
            await asyncio.sleep(0)

        # 7. Send node context metadata before response
        if context_result.node_ids:
            final_node_ids = context_result.node_ids
            final_node_titles = context_result.node_titles
            yield sse("context", {
                "node_ids": context_result.node_ids,
                "node_titles": context_result.node_titles,
            })

        # 8. Build messages for LLM — include memory context
        combined_context = context_result.context
        if memory_context:
            if combined_context:
                combined_context += "\n\n" + memory_context
            else:
                combined_context = memory_context

        messages = build_messages(
            user_message=req.message,
            context=combined_context,
            history=req.history,
        )

        # 9. Stream LLM response token by token
        async for token in engine.stream(messages):
            full_response.append(token)
            yield sse("token", {"content": token})

        # 10. Done — send final node citations + session_id so frontend can track it
        yield sse("done", {
            "node_ids": final_node_ids,
            "node_titles": final_node_titles,
            "session_id": session_id,
        })

        # 11. Save assistant message to DB
        assistant_content = "".join(full_response)
        _save_message_sync(
            session_id, "assistant", assistant_content,
            tool_calls=tool_calls_list if tool_calls_list else None,
            node_ids=final_node_ids if final_node_ids else None,
            node_titles=final_node_titles if final_node_titles else None,
        )

        # 12. Background: extract memory facts from this exchange
        if req.message and assistant_content:
            background_tasks.add_task(
                _extract_and_store_memory,
                req.message,
                assistant_content,
                session_id,
                engine.complete,
            )

        # 13. Background: learn from errors if the response indicates a mistake
        if req.message and assistant_content:
            background_tasks.add_task(
                _learn_from_error,
                req.message,
                assistant_content,
                engine.complete,
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
