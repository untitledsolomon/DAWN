import json
import asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from config import settings
from llm.engine import get_engine, build_messages
from llm.tools import build_context, extract_memory_facts
import db.client as db

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]
    session_id: Optional[str] = None


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(event_type: str, payload) -> str:
    """Format a single SSE event."""
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ── Main chat endpoint ────────────────────────────────────────────────────────

@router.post("/")
async def chat(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    engine = get_engine()
    full_response = []

    async def generate():
        nonlocal full_response

        # 1. Show thinking state
        yield sse("thinking", {"content": "Searching knowledge graph..."})
        await asyncio.sleep(0)  # Flush buffer

        # 2. Build context from graph
        context_result = await build_context(req.message)

        # 3. Stream tool call events to frontend
        for tc in context_result.tool_calls:
            yield sse("tool", {
                "name": tc.name,
                "args": tc.args,
                "result_count": tc.result_count,
            })
            await asyncio.sleep(0)

        # 4. Send node context metadata before response
        if context_result.node_ids:
            yield sse("context", {
                "node_ids": context_result.node_ids,
                "node_titles": context_result.node_titles,
            })

        # 5. Build messages for LLM
        messages = build_messages(
            user_message=req.message,
            context=context_result.context,
            history=req.history,
        )

        # 6. Stream LLM response token by token
        async for token in engine.stream(messages):
            full_response.append(token)
            yield sse("token", {"content": token})

        # 7. Done — send final node citations
        yield sse("done", {
            "node_ids": context_result.node_ids,
            "node_titles": context_result.node_titles,
        })

        # 8. Background: extract memory facts from this exchange
        if req.message:
            background_tasks.add_task(
                _extract_and_store_memory,
                req.message,
                "".join(full_response),
                req.session_id or "unknown",
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


# ── Background memory task ────────────────────────────────────────────────────

async def _extract_and_store_memory(
    user_message: str,
    assistant_response: str,
    session_id: str,
    llm_complete_fn,
):
    conversation = f"User: {user_message}\nDAWN: {assistant_response}"
    facts = await extract_memory_facts(conversation, llm_complete_fn)

    if not facts:
        return

    # Create a memory session
    session = await db.create_memory_session(
        source="dawn_web",
        summary=user_message[:100],
    )

    # Store each fact as a draft memory node for review
    for fact in facts[:5]:
        node = await db.create_node({
            "title": fact.get("title", "Memory fact"),
            "type": "memory",
            "body": fact.get("body", ""),
            "status": "draft",
            "source": "conversation",
            "source_ref": session_id,
            "confidence": 0.7,
        })

        if node.get("id") and session.get("id"):
            await db.link_memory_node(node["id"], session["id"])

        # Attach tags
        for tag_name in fact.get("tags", []):
            all_tags = await db.get_all_tags()
            tag = next((t for t in all_tags if t["name"] == tag_name), None)
            if tag:
                await db.attach_tag(node["id"], tag["id"])
