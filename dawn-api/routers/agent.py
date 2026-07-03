import json
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from config import settings
from llm.agent import run_agent_loop, DEFAULT_MAX_ITERATIONS
from llm.identity import resolve_identity, Identity, TrustTier

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
    identity: Identity = Depends(get_identity),
):
    async def generate():
        async for event in run_agent_loop(
            user_message=req.message,
            identity=identity,
            history=req.history,
            max_iterations=req.max_iterations,
        ):
            event_type = event.pop("type")
            yield sse(event_type, event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
