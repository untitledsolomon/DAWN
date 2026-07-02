from fastapi import APIRouter, Depends, HTTPException, Header, Query
from typing import Optional
from config import settings
import db.client as db

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, le=50),
    _: None = Depends(verify_key),
):
    """
    Fuzzy search across node titles and bodies.
    Used by the nodes page search bar.
    """
    results = await db.rpc_fuzzy_search(q, limit=limit, threshold=0.1)
    return results or []


@router.get("/tag/{tag_name}")
async def search_by_tag(tag_name: str, _: None = Depends(verify_key)):
    results = await db.rpc_search_tags(tag_name)
    return results or []


@router.get("/traverse/{node_id}")
async def traverse(
    node_id: str,
    depth: int = Query(2, ge=1, le=4),
    relations: Optional[str] = Query(None),  # comma-separated relation types
    _: None = Depends(verify_key),
):
    """Traverse the graph from a given node. Used by the graph explorer."""
    relation_list = [r.strip() for r in relations.split(",")] if relations else None
    results = await db.rpc_traverse(node_id, relations=relation_list, max_depth=depth)
    return results or []
