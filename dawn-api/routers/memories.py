"""DAWN Memories API — CRUD for the `memories` table (personal facts about the user)."""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ──────────────────────────────────────────────────────────────────

class MemoryCreate(BaseModel):
    title: str
    body: Optional[str] = None
    fact_type: str = "fact"
    confidence: float = 0.7
    source: str = "manual"
    tags: list[str] = []


class MemoryUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    fact_type: Optional[str] = None
    confidence: Optional[float] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/")
async def list_memories(
    status: str = Query("active"),
    fact_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    _: None = Depends(verify_key),
):
    """List memories, optionally filtered by status and fact_type."""
    if status == "active":
        return await db.get_active_memories(limit=limit, offset=offset)
    elif status == "draft":
        return await db.get_draft_memories(limit=limit)
    elif status == "all":
        # Return all memories regardless of status
        return await db.get_all_memories(limit=limit, offset=offset)
    return await db.get_active_memories(limit=limit, offset=offset)


@router.get("/count")
async def count_memories(
    status: str = Query("active"),
    _: None = Depends(verify_key),
):
    """Return the total number of memories matching the given status."""
    total = await db.count_memories(status=status)
    return {"total": total}


@router.post("/")
async def create_memory(payload: MemoryCreate, _: None = Depends(verify_key)):
    """Create a new memory fact."""
    memory = await db.create_memory(
        title=payload.title,
        body=payload.body,
        fact_type=payload.fact_type,
        confidence=payload.confidence,
        source=payload.source,
        tags=payload.tags if payload.tags else None,
    )
    if not memory.get("id"):
        raise HTTPException(status_code=500, detail="Memory creation failed")
    return memory


@router.get("/{memory_id}")
async def get_memory(memory_id: str, _: None = Depends(verify_key)):
    """Get a single memory by ID."""
    memory = await db.get_memory_by_id(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.put("/{memory_id}")
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    _: None = Depends(verify_key),
):
    """Update a memory."""
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    memory = await db.update_memory(memory_id, data)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, _: None = Depends(verify_key)):
    """Delete a memory."""
    await db.delete_memory(memory_id)
    return {"deleted": memory_id}


@router.post("/{memory_id}/approve")
async def approve_memory(memory_id: str, _: None = Depends(verify_key)):
    """Approve a draft memory (set status to active)."""
    memory = await db.update_memory(memory_id, {"status": "active", "confidence": 0.85})
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("/{memory_id}/reject")
async def reject_memory(memory_id: str, _: None = Depends(verify_key)):
    """Reject a draft memory (archive it)."""
    memory = await db.update_memory(memory_id, {"status": "archived"})
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("/consolidate")
async def consolidate_memories_endpoint(_: None = Depends(verify_key)):
    """Run memory consolidation (merge duplicates)."""
    result = await db.consolidate_memories()
    return result
