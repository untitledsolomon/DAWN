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
from llm.tools import build_context, extract_memory_facts, extract_error_pattern, extract_key_terms, load_memory_context, extract_and_store_memory
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ─────────────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: Optional[str] = None
    web_search_enabled: bool = False


# ── SSE helpers ──────────────────────────────────────────────────────────────

def sse(event_type: str, payload) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ── DB helpers ───────────────────────────────────────────────────────────────

def _save_message_sync(session_id: str, role: str, content: str,
                       tool_calls: Optional[list] = None,
                       node_ids: Optional[list[str]] = None,
                       node_titles: Optional[list[str]] = None,
                       artifact_ids: Optional[list[str]] = None) -> dict:
    """Insert a message into chat_messages (sync — called from async generator)."""
    try:
        supabase = db.get_db()
        data = {
            "session_id": session_id,
            "role": role,
            "content": content,
        }
        if tool_calls:
            data["tool_calls"] = tool_calls
        if node_ids:
            data["node_ids"] = node_ids
        if node_titles:
            data["node_titles"] = node_titles
        if artifact_ids:
            data["artifact_ids"] = artifact_ids
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
    (re)titled from the first real message."""
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


async def _link_node_to_related(node_id: str, title: str, max_links: int = 3) -> None:
    """Best-effort: connect a freshly-created node to existing related nodes
    via 'related_to' edges."""
    if not title:
        return
    try:
        matches = await db.rpc_fuzzy_search(title, limit=max_links + 1, threshold=0.3)
        linked = 0
        for match in matches:
            match_id = match.get("id")
            if not match_id or match_id == node_id:
                continue
            try:
                db.get_db().table("edges").insert({
                    "from_node": node_id,
                    "to_node": match_id,
                    "relation": "related_to",
                    "source": "conversation",
                    "note": "auto-linked from conversation memory extraction",
                }).execute()
                linked += 1
            except Exception as e:
                logger.warning(f"[memory] Failed to create edge {node_id} -> {match_id}: {e}")
            if linked >= max_links:
                break
        if linked:
            logger.info(f"[memory] Linked new node {node_id} to {linked} related node(s)")
    except Exception as e:
        logger.warning(f"[memory] Related-node lookup failed for node {node_id}: {e}")


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


# ── Main chat endpoint ───────────────────────────────────────────────────────

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

        # 2. Auto-title on first message
        if _needs_title_sync(session_id):
            background_tasks.add_task(_generate_title, session_id, req.message, engine.complete)

        # 3. Show thinking state
        yield sse("thinking", {"content": "Searching knowledge graph..."})
        await asyncio.sleep(0)

        # 4. Load memory context (personal facts, preferences, past learnings)
        #    Uses the new dedicated memories table via load_memory_context()
        memory_context = await load_memory_context(req.message)

        # 5. Build context from graph
        context_result = await build_context(req.message, web_search_enabled=req.web_search_enabled)

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

        # Add web search context note if enabled
        if req.web_search_enabled:
            web_note = (
                "\n\n[Web Search Enabled] You have access to web_search tool. "
                "Use it when the knowledge graph doesn't have sufficient information "
                "on the user's query. Search the web for current, up-to-date information."
            )
            if combined_context:
                combined_context += web_note
            else:
                combined_context = web_note

        messages = build_messages(
            user_message=req.message,
            context=combined_context,
            history=req.history,
        )

        # 9. Stream LLM response token by token
        async for token in engine.stream(messages):
            full_response.append(token)
            yield sse("token", {"content": token})

        # 10. Done — send final node citations + session_id
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

        # 12. Background: extract memory facts into dedicated memories table
        if req.message and assistant_content:
            background_tasks.add_task(
                extract_and_store_memory,
                f"User: {req.message}\nDAWN: {assistant_content}",
                engine.complete,
                session_id,
            )

        # 13. Background: learn from errors
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
