"""Library API — documents, search, ingest, jobs."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from config import settings as app_settings
from library import store

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class IngestUrlBody(BaseModel):
    url: str
    title: Optional[str] = None
    kind: str = "docs_page"
    collection: Optional[str] = None


@router.get("/library/documents", tags=["library"])
async def list_documents(status: Optional[str] = None, limit: int = Query(100, le=200),
                         _: None = Depends(verify_key)):
    return await store.list_documents(status=status, limit=limit)


@router.get("/library/search", tags=["library"])
async def search_documents(q: str, limit: int = Query(6, le=20), _: None = Depends(verify_key)):
    rows = await store.search_chunks(q, limit=limit)
    await store.log_access(None, "user", "search", query=q, result_count=len(rows))
    return {"results": rows, "count": len(rows), "_untrusted": True}


@router.post("/library/ingest-url", tags=["library"])
async def ingest_url_req(req: IngestUrlBody, _: None = Depends(verify_key)):
    from library.pipeline import ingest_url
    result = await ingest_url(req.url, kind=req.kind, title=req.title,
                              collection_name=req.collection, requested_by="user")
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("error", "ingest failed"))
    await store.log_access(None, "user", "ingest", query=req.url)
    return result


@router.get("/library/jobs", tags=["library"])
async def list_ingest_jobs(limit: int = Query(50, le=200), _: None = Depends(verify_key)):
    import db.client as db
    res = await db._async_execute(
        lambda: db.get_db().table("ingest_jobs").select("*").order("created_at", desc=True).limit(limit).execute()
    )
    return res.data or []
