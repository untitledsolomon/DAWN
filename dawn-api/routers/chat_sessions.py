"""
Chat session management — CRUD for sessions and messages.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ──────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    title: str = "New Chat"


class UpdateSessionRequest(BaseModel):
    title: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    tool_calls: Optional[list] = None
    node_ids: Optional[list[str]] = None
    node_titles: Optional[list[str]] = None
    created_at: str


class SessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0


def get_message_count(supabase, session_id: str) -> int:
    """Get message count for a session, handling different Supabase client versions."""
    try:
        res = supabase.table("chat_messages").select("id", count="exact").eq("session_id", session_id).execute()
        # Supabase v2 returns count as an attribute on the response
        if hasattr(res, 'count') and res.count is not None:
            return res.count
        # Fallback: count the data array
        if res.data:
            return len(res.data)
        return 0
    except Exception as e:
        logger.warning(f"[chat_sessions] Failed to get message count: {e}")
        return 0


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(_: None = Depends(verify_key)):
    """List all chat sessions, most recent first, with message count."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_sessions").select(
            "id, title, created_at, updated_at"
        ).order("updated_at", desc=True).execute()
        sessions = res.data or []

        result = []
        for s in sessions:
            count = get_message_count(supabase, s["id"])
            result.append({
                **s,
                "message_count": count,
            })
        return result
    except Exception as e:
        logger.error(f"[chat_sessions] list_sessions failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@router.post("/sessions", response_model=SessionResponse)
async def create_session(
    req: CreateSessionRequest,
    _: None = Depends(verify_key),
):
    """Create a new chat session."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_sessions").insert({
            "title": req.title,
        }).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create session")
        return {**res.data[0], "message_count": 0}
    except Exception as e:
        logger.error(f"[chat_sessions] create_session failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    _: None = Depends(verify_key),
):
    """Get a single session by ID."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_sessions").select("*").eq("id", session_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Session not found")
        count = get_message_count(supabase, session_id)
        return {**res.data[0], "message_count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[chat_sessions] get_session failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session: {str(e)}")


@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    req: UpdateSessionRequest,
    _: None = Depends(verify_key),
):
    """Rename a session."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_sessions").update({
            "title": req.title,
        }).eq("id", session_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Session not found")
        count = get_message_count(supabase, session_id)
        return {**res.data[0], "message_count": count}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[chat_sessions] update_session failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update session: {str(e)}")


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    _: None = Depends(verify_key),
):
    """Delete a session and all its messages (CASCADE)."""
    try:
        supabase = db.get_db()
        supabase.table("chat_sessions").delete().eq("id", session_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"[chat_sessions] delete_session failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")


@router.get("/sessions/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    _: None = Depends(verify_key),
):
    """Get all messages for a session, oldest first."""
    try:
        supabase = db.get_db()
        res = supabase.table("chat_messages").select(
            "id, session_id, role, content, tool_calls, node_ids, node_titles, created_at"
        ).eq("session_id", session_id).order("created_at").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[chat_sessions] get_session_messages failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")
