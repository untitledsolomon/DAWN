import json
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from config import settings
from llm.agent import run_agent_loop, DEFAULT_MAX_ITERATIONS
from llm.identity import resolve_identity, Identity, TrustTier
from llm.engine import get_engine
import db.client as db

# Reuse the exact same persistence + title helpers routers/chat.py uses, so
# Chat mode and Agent mode sessions/messages/titles behave identically.
from routers.chat import (
    _save_message_sync,
    _ensure_session_sync,
    _generate_title,
    _needs_title_sync,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ─────────────────────────────────────────────────────────────────────
# Unlike routers/chat.py's verify_key (which only checks the key is valid),
# this resolves *which* identity is making the request, since agent mode's
# tool access is tiered — see llm/identity.py.

def get_identity(x_api_key: Optional[str] = Header(None)) -> Identity:
    identity = resolve_identity(x_api_key)
    if identity.tier == TrustTier.UNKNOWN:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return identity


# ── Schema ───────────────────────────────────────────────────────────────────

class AgentRequest(BaseModel):
    message: str
    history: list[dict] = []
    session_id: Optional[str] = None
    max_iterations: int = DEFAULT_MAX_ITERATIONS


# ── SSE helper ───────────────────────────────────────────────────────────────
# Identical format to routers/chat.py's sse() — duplicated here rather than
# imported to avoid a cross-router dependency; consider moving to a shared
# util if a third SSE router shows up.

def sse(event_type: str, payload: dict) -> str:
    return f"data: {json.dumps({'type': event_type, **payload})}\n\n"


# ── Main agent endpoint ──────────────────────────────────────────────────────

@router.post("/")
async def agent(
    req: AgentRequest,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(get_identity),
):
    engine = get_engine()

    # Ensure we have a session, exactly like /chat/ does.
    session_id = _ensure_session_sync(req.session_id)

    tool_calls_list: list[dict] = []
    full_response: list[str] = []
    # Track artifact IDs created during this turn so we can save them on the message
    artifact_ids_this_turn: list[str] = []

    async def generate():
        nonlocal full_response, tool_calls_list, artifact_ids_this_turn

        # 1. Save user message immediately
        _save_message_sync(session_id, "user", req.message)

        # 2. Auto-title on first message (using AI) — retitle whenever the
        # session still has its placeholder title, same as chat mode. This
        # also self-heals any session left stuck at "New Chat" from before.
        if _needs_title_sync(session_id):
            background_tasks.add_task(
                _generate_title, session_id, req.message, engine.complete
            )

        # Track tool calls by a unique key (name + index) so duplicate tool
        # names don't overwrite each other in pending_calls.
        pending_calls: dict[str, dict] = {}
        tool_call_counter: dict[str, int] = {}

        async for event in run_agent_loop(
            user_message=req.message,
            identity=identity,
            history=req.history,
            max_iterations=req.max_iterations,
        ):
            event_type = event.pop("type")

            if event_type == "tool_call":
                name = event.get("name", "unknown")
                # Build a unique key: "create_chart#0", "create_chart#1", etc.
                counter = tool_call_counter.get(name, 0)
                tool_call_counter[name] = counter + 1
                key = f"{name}#{counter}"

                tc_dict = {"name": name, "args": event.get("args")}
                tool_calls_list.append(tc_dict)
                pending_calls[key] = tc_dict

            elif event_type == "tool_result":
                name = event.get("name", "unknown")
                # Find the first pending call with this name that doesn't have
                # a result yet (by iterating keys in insertion order).
                matched_key = None
                for k, v in pending_calls.items():
                    if k.startswith(f"{name}#") and "success" not in v:
                        matched_key = k
                        break

                if matched_key:
                    tc_dict = pending_calls[matched_key]
                    tc_dict["success"] = event.get("success")
                    tc_dict["output"] = event.get("output")
                    tc_dict["error"] = event.get("error")

                # The create_chart tool only builds a spec — it doesn't know the
                # session_id, so persisting it into `artifacts` and telling the
                # frontend about it happens here, where we have both.
                if (
                    event.get("name") == "create_chart"
                    and event.get("success")
                    and isinstance(event.get("output"), dict)
                ):
                    output = event["output"]
                    try:
                        artifact = await db.create_artifact(
                            session_id=session_id,
                            type="chart",
                            title=output.get("title") or "Chart",
                            description=output.get("description"),
                            spec=output.get("spec"),
                        )
                        if artifact and artifact.get("id"):
                            artifact_ids_this_turn.append(artifact["id"])
                            # Shape must match AgentSSEEvent's "artifact" variant
                            # in dawn-ui/src/lib/agent-types.ts exactly.
                            yield sse("artifact", {
                                "artifact_id": artifact.get("id"),
                                "artifact_type": artifact.get("type", "chart"),
                                "title": artifact.get("title"),
                                "spec": artifact.get("spec"),
                                "url": artifact.get("url"),
                            })
                    except Exception:
                        logger.exception("Failed to persist chart artifact")

            elif event_type == "token":
                full_response.append(event.get("content", ""))

            elif event_type == "done":
                # Prefer the fully assembled content if we captured tokens;
                # fall back to whatever run_agent_loop reports as final content.
                event["content"] = "".join(full_response) or event.get("content", "")
                # Let the frontend know which session this landed in, same
                # contract as /chat/'s "done" event.
                event["session_id"] = session_id

            yield sse(event_type, event)

        # 3. Save assistant message to DB once the stream is complete
        assistant_content = "".join(full_response)
        if assistant_content:
            _save_message_sync(
                session_id,
                "assistant",
                assistant_content,
                tool_calls=tool_calls_list if tool_calls_list else None,
                artifact_ids=artifact_ids_this_turn if artifact_ids_this_turn else None,
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
