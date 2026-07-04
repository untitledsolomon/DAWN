"""
Books & Learning endpoints — manage book library, learning sessions, knowledge gaps.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class BookCreate(BaseModel):
    title: str
    author: Optional[str] = None
    isbn: Optional[str] = None
    category: Optional[str] = None
    tags: list[str] = []
    notes: Optional[str] = None


@router.get("/books", tags=["books"])
async def list_books(category: Optional[str] = None, _: None = Depends(verify_key)):
    """List all books in the library."""
    try:
        supabase = db.get_db()
        q = supabase.table("books").select("*").order("title")
        if category:
            q = q.eq("category", category)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list books: {e}")
        return []


@router.post("/books", tags=["books"])
async def add_book(req: BookCreate, _: None = Depends(verify_key)):
    """Add a new book to the library."""
    try:
        supabase = db.get_db()
        res = supabase.table("books").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to add book")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/books/{book_id}", tags=["books"])
async def get_book(book_id: str, _: None = Depends(verify_key)):
    """Get a single book."""
    try:
        supabase = db.get_db()
        res = supabase.table("books").select("*").eq("id", book_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Book not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/books/{book_id}", tags=["books"])
async def delete_book(book_id: str, _: None = Depends(verify_key)):
    """Delete a book."""
    try:
        supabase = db.get_db()
        supabase.table("books").delete().eq("id", book_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/books/{book_id}/ingest", tags=["books"])
async def ingest_book(book_id: str, _: None = Depends(verify_key)):
    """Trigger ingestion of a book into the knowledge graph."""
    try:
        supabase = db.get_db()
        supabase.table("books").update({
            "ingestion_status": "ingesting",
        }).eq("id", book_id).execute()
        
        # TODO: Actual book ingestion pipeline
        # For now, mark as complete
        supabase.table("books").update({
            "ingestion_status": "complete",
            "ingested": True,
        }).eq("id", book_id).execute()
        
        return {"status": "ingestion_started", "book_id": book_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/learning/sessions", tags=["books"])
async def list_learning_sessions(limit: int = 20, _: None = Depends(verify_key)):
    """List learning sessions."""
    try:
        supabase = db.get_db()
        res = supabase.table("learning_sessions").select("*, books(title, author)").order(
            "created_at", desc=True
        ).limit(limit).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list learning sessions: {e}")
        return []


@router.get("/knowledge-gaps", tags=["books"])
async def list_knowledge_gaps(_: None = Depends(verify_key)):
    """List identified knowledge gaps."""
    try:
        supabase = db.get_db()
        res = supabase.table("knowledge_gaps").select("*").order("frequency", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list knowledge gaps: {e}")
        return []


@router.post("/knowledge-gaps/{gap_id}/address", tags=["books"])
async def address_knowledge_gap(gap_id: str, _: None = Depends(verify_key)):
    """Mark a knowledge gap as addressed."""
    try:
        supabase = db.get_db()
        supabase.table("knowledge_gaps").update({
            "is_addressed": True,
            "addressed_at": "now()",
        }).eq("id", gap_id).execute()
        return {"status": "addressed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
