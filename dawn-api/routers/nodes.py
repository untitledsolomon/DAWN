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

class NodeCreate(BaseModel):
    title: str
    type: str
    body: Optional[str] = None
    status: str = "active"
    source: str = "manual"
    confidence: float = 1.0
    tags: list[str] = []


class NodeUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[float] = None
    tags: Optional[list[str]] = None


class EdgeCreate(BaseModel):
    from_node: str
    to_node: str
    relation: str
    weight: float = 1.0
    note: Optional[str] = None


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/")
async def list_nodes(
    status: str = Query("active"),
    type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    source_ref: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    _: None = Depends(verify_key),
):
    return await db.list_nodes(status=status, node_type=type, tag=tag, limit=limit, offset=offset, source_ref=source_ref)


@router.get("/count")
async def count_nodes(
    status: str = Query("active"),
    type: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    _: None = Depends(verify_key),
):
    """Return the total number of nodes matching the given filters."""
    total = await db.count_nodes(status=status, node_type=type, tag=tag)
    return {"total": total}


@router.post("/")
async def create_node(payload: NodeCreate, _: None = Depends(verify_key)):
    # Create the node
    node_data = payload.model_dump(exclude={"tags"})
    node = await db.create_node(node_data)

    if not node.get("id"):
        raise HTTPException(status_code=500, detail="Node creation failed")

    # Attach tags
    all_tags = await db.get_all_tags()
    for tag_name in payload.tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
        await db.attach_tag(node["id"], tag["id"])

    return node


@router.get("/tags")
async def list_tags(_: None = Depends(verify_key)):
    return await db.get_all_tags()


@router.post("/tags")
async def create_tag(
    payload: dict,
    _: None = Depends(verify_key),
):
    return await db.create_tag(
        name=payload.get("name", ""),
        description=payload.get("description", ""),
    )


@router.get("/{node_id}")
async def get_node(node_id: str, _: None = Depends(verify_key)):
    node = await db.rpc_get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.put("/{node_id}")
async def update_node(
    node_id: str,
    payload: NodeUpdate,
    _: None = Depends(verify_key),
):
    data = {k: v for k, v in payload.model_dump().items() if v is not None and k != "tags"}
    node = await db.update_node(node_id, data)

    # Re-attach tags if provided
    if payload.tags is not None:
        # Remove existing tags and re-add
        db_client = db.get_db()
        db_client.table("node_tags").delete().eq("node_id", node_id).execute()
        all_tags = await db.get_all_tags()
        for tag_name in payload.tags:
            tag = next((t for t in all_tags if t["name"] == tag_name), None)
            if not tag:
                tag = await db.create_tag(tag_name)
            await db.attach_tag(node_id, tag["id"])

    return node


@router.delete("/{node_id}")
async def delete_node(node_id: str, _: None = Depends(verify_key)):
    await db.delete_node(node_id)
    return {"deleted": node_id}


# ── Edges ───────────────────────────────────────────────────────────────────

@router.post("/edges/")
async def create_edge(payload: EdgeCreate, _: None = Depends(verify_key)):
    return await db.create_edge(payload.model_dump())


@router.delete("/edges/{edge_id}")
async def delete_edge(edge_id: str, _: None = Depends(verify_key)):
    await db.delete_edge(edge_id)
    return {"deleted": edge_id}


# ── Memory review ───────────────────────────────────────────────────────────

@router.get("/memory/pending")
async def get_pending(_: None = Depends(verify_key)):
    return await db.get_pending_review()


@router.post("/{node_id}/approve")
async def approve_node(node_id: str, _: None = Depends(verify_key)):
    return await db.update_node(node_id, {"status": "active"})


@router.post("/{node_id}/reject")
async def reject_node(node_id: str, _: None = Depends(verify_key)):
    return await db.update_node(node_id, {"status": "archived"})
