"""
Books & Learning endpoints — manage book library, learning sessions, knowledge gaps.
v2.1 — Async ingestion: POST /books/{id}/ingest returns job_id immediately (no blocking poll).
         Frontend polls GET /ingest/status/{job_id} to track completion.
         Delete cascade: deleting a book also removes its ingested knowledge graph nodes.
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
    """Delete a book and cascade-delete its ingested knowledge graph nodes."""
    try:
        supabase = db.get_db()

        # Get the book first to check if it has ingested content
        book_res = supabase.table("books").select("id, title, ingested").eq("id", book_id).execute()
        if not book_res.data:
            raise HTTPException(status_code=404, detail="Book not found")

        book = book_res.data[0]

        # Cascade: delete any knowledge graph nodes associated with this book
        if book.get("ingested"):
            try:
                # Find nodes with source_ref matching the book title or id
                nodes_res = supabase.table("nodes").select("id").or_(
                    f"source_ref.eq.{book['title']},source_ref.eq.{book_id}"
                ).execute()
                for node in (nodes_res.data or []):
                    # Delete node_tags first
                    supabase.table("node_tags").delete().eq("node_id", node["id"]).execute()
                    # Delete edges
                    supabase.table("edges").delete().or_(
                        f"from_node.eq.{node['id']},to_node.eq.{node['id']}"
                    ).execute()
                    # Delete the node
                    supabase.table("nodes").delete().eq("id", node["id"]).execute()
                logger.info(f"Cascade deleted {len(nodes_res.data or [])} nodes for book '{book['title']}'")
            except Exception as e:
                logger.warning(f"Cascade delete for book {book_id} had partial errors: {e}")

        # Delete the book itself
        supabase.table("books").delete().eq("id", book_id).execute()
        return {"status": "deleted", "book_id": book_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/books/{book_id}/ingest", tags=["books"])
async def ingest_book(book_id: str, _: None = Depends(verify_key)):
    """Trigger ingestion of a book into the knowledge graph.

    Returns a job_id immediately. Frontend polls GET /ingest/status/{job_id}
    to track completion. When the job completes, the book's ingestion_status
    is updated in the database.
    """
    try:
        supabase = db.get_db()

        # Get the book
        book_res = supabase.table("books").select("*").eq("id", book_id).execute()
        if not book_res.data:
            raise HTTPException(status_code=404, detail="Book not found")

        book = book_res.data[0]

        # Mark as ingesting
        supabase.table("books").update({
            "ingestion_status": "ingesting",
        }).eq("id", book_id).execute()

        # Delegate to the real ingestor
        from routers.ingest import ingestion_queue, IngestionJob
        import uuid

        title = book.get("title", "Untitled")
        tags = book.get("tags", [])
        if book.get("category"):
            tags = list(set(list(tags) + [book["category"]]))

        # Build content from available fields
        content_parts = [title]
        if book.get("author"):
            content_parts.append(f"Author: {book['author']}")
        if book.get("notes"):
            content_parts.append(book["notes"])
        if book.get("summary"):
            content_parts.append(book["summary"])

        content = "\n\n".join(content_parts)

        # Queue a document ingestion job
        job = IngestionJob(
            id=str(uuid.uuid4()),
            type="document",
            params={
                "title": title,
                "content": content,
                "source_ref": book_id,
                "tags": tags,
            }
        )
        await ingestion_queue.enqueue(job)

        # Return immediately with the job_id — frontend polls for status
        return {
            "status": "queued",
            "job_id": job.id,
            "book_id": book_id,
            "message": "Book ingestion queued. Poll GET /ingest/status/{job_id} for completion.",
        }

    except HTTPException:
        raise
    except Exception as e:
        # Mark as error if we couldn't even queue it
        try:
            supabase.table("books").update({
                "ingestion_status": "error",
            }).eq("id", book_id).execute()
        except Exception:
            pass
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
