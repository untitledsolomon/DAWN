"""
DAWN Database Client - async-safe Supabase operations for the knowledge graph.

The supabase-py client (v2.4.6) is synchronous. All DB operations are
wrapped in asyncio.to_thread() so they don't block the event loop.
Batch operations use single multi-row inserts/updates wherever possible.
"""
from supabase import create_client, Client
from config import settings
from typing import Optional
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


async def _async_execute(operation):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, operation)


async def create_node(data: dict) -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("nodes").insert(data).execute())
    return res.data[0] if res.data else {}


async def create_nodes_batch(rows: list[dict], batch_size: int = 200) -> list[dict]:
    if not rows:
        return []
    db = get_db()
    created = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        res = await _async_execute(lambda b=batch: db.table("nodes").insert(b).execute())
        created.extend(res.data or [])
    return created


async def get_node_by_id(node_id: str) -> Optional[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.rpc("get_node", {"p_id": node_id}).execute())
    return res.data


async def update_node(node_id: str, data: dict) -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("nodes").update(data).eq("id", node_id).execute())
    return res.data[0] if res.data else {}


async def delete_node(node_id: str) -> bool:
    db = get_db()
    await _async_execute(lambda: db.table("nodes").delete().eq("id", node_id).execute())
    return True


async def list_nodes(status: str = "active", node_type: Optional[str] = None,
                      tag: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    db = get_db()
    q = db.table("nodes").select(
        "id, title, type, body, status, source, confidence, created_at, updated_at, node_tags(tags(name))"
    ).eq("status", status).order("created_at", desc=True).limit(limit).offset(offset)
    if node_type:
        q = q.eq("type", node_type)
    res = await _async_execute(lambda: q.execute())
    nodes = res.data or []
    for node in nodes:
        raw_tags = node.pop("node_tags", []) or []
        node["tags"] = [t["tags"]["name"] for t in raw_tags if t.get("tags")]
    if tag:
        nodes = [n for n in nodes if tag in n.get("tags", [])]
    return nodes


async def create_edge(data: dict) -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("edges").insert(data).execute())
    return res.data[0] if res.data else {}


async def create_edges_batch(rows: list[dict], batch_size: int = 200) -> list[dict]:
    if not rows:
        return []
    db = get_db()
    created = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        res = await _async_execute(lambda b=batch: db.table("edges").insert(b).execute())
        created.extend(res.data or [])
    return created


async def delete_edge(edge_id: str) -> bool:
    db = get_db()
    await _async_execute(lambda: db.table("edges").delete().eq("id", edge_id).execute())
    return True


async def get_nodes_by_source_ref_prefix(prefix: str, limit: int = 5000) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: (
        db.table("nodes")
        .select("id, title, source_ref, status")
        .like("source_ref", f"{prefix}%")
        .in_("status", ["active", "stale"])
        .limit(limit)
        .execute()
    ))
    return res.data or []


async def archive_nodes_batch(node_ids_and_titles: list[tuple], batch_size: int = 200):
    """Archive prior nodes from a re-ingested source using batched updates."""
    if not node_ids_and_titles:
        return
    db = get_db()
    for i in range(0, len(node_ids_and_titles), batch_size):
        batch = node_ids_and_titles[i:i + batch_size]
        for node_id, old_title in batch:
            new_title = f"[archived {node_id[:8]}] {old_title}"[:250]
            await _async_execute(lambda nid=node_id, nt=new_title: (
                db.table("nodes").update({"status": "archived", "title": nt}).eq("id", nid).execute()
            ))


async def update_node_embeddings(node_id_to_embedding: dict, batch_size: int = 50) -> int:
    if not node_id_to_embedding:
        return 0
    db = get_db()
    updated = 0
    items = list(node_id_to_embedding.items())
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        for node_id, embedding in batch:
            if embedding is None:
                continue
            try:
                await _async_execute(lambda nid=node_id, emb=embedding: (
                    db.table("nodes").update({"embedding": emb}).eq("id", nid).execute()
                ))
                updated += 1
            except Exception as e:
                logger.error(f"Failed to write embedding for node {node_id}: {e}")
    return updated


async def get_all_tags() -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.table("tags").select("*").order("name").execute())
    return res.data or []


async def create_tag(name: str, description: str = "") -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("tags").insert({"name": name, "description": description}).execute())
    return res.data[0] if res.data else {}


async def attach_tag(node_id: str, tag_id: str):
    db = get_db()
    await _async_execute(lambda: db.table("node_tags").upsert({"node_id": node_id, "tag_id": tag_id}).execute())


async def attach_tags_batch(node_ids: list[str], tag_ids: list[str], batch_size: int = 500):
    if not node_ids or not tag_ids:
        return
    db = get_db()
    rows = [{"node_id": nid, "tag_id": tid} for nid in node_ids for tid in tag_ids]
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        await _async_execute(lambda b=batch: db.table("node_tags").upsert(b).execute())


async def rpc_get_node(node_id: str) -> Optional[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.rpc("get_node", {"p_id": node_id}).execute())
    return res.data


async def rpc_traverse(start_id: str, relations: Optional[list[str]] = None, max_depth: int = 2) -> list[dict]:
    db = get_db()
    params = {"p_start_id": start_id, "p_max_depth": max_depth}
    if relations:
        params["p_relations"] = relations
    res = await _async_execute(lambda: db.rpc("traverse", params).execute())
    return res.data or []


async def rpc_fuzzy_search(query: str, limit: int = 5, threshold: float = 0.2,
                            exclude_types: Optional[list[str]] = None,
                            exclude_tags: Optional[list[str]] = None) -> list[dict]:
    db = get_db()
    params = {"p_query": query, "p_limit": limit, "p_threshold": threshold}
    if exclude_types:
        params["p_exclude_types"] = exclude_types
    if exclude_tags:
        params["p_exclude_tags"] = exclude_tags
    try:
        res = await _async_execute(lambda: db.rpc("fuzzy_search", params).execute())
        return res.data or []
    except Exception as e:
        if (exclude_types or exclude_tags) and "p_exclude" in str(e):
            logger.warning("fuzzy_search exclude filters not available - falling back to unfiltered.")
            res = await _async_execute(lambda: db.rpc("fuzzy_search",
                {"p_query": query, "p_limit": limit, "p_threshold": threshold}).execute())
            return res.data or []
        raise


async def rpc_fuzzy_search_code(query: str, limit: int = 5, threshold: float = 0.2) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.rpc("fuzzy_search_code",
        {"p_query": query, "p_limit": limit, "p_threshold": threshold}).execute())
    return res.data or []


async def rpc_search_tags(tag_name: str) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.rpc("search_tags", {"p_tag_name": tag_name}).execute())
    return res.data or []


async def rpc_semantic_search(embedding: list[float], limit: int = 5,
                               exclude_types: Optional[list[str]] = None,
                               exclude_tags: Optional[list[str]] = None) -> list[dict]:
    db = get_db()
    params = {"p_embedding": embedding, "p_limit": limit}
    if exclude_types:
        params["p_exclude_types"] = exclude_types
    if exclude_tags:
        params["p_exclude_tags"] = exclude_tags
    try:
        res = await _async_execute(lambda: db.rpc("semantic_search", params).execute())
        return res.data or []
    except Exception as e:
        if (exclude_types or exclude_tags) and "p_exclude" in str(e):
            logger.warning("semantic_search exclude filters not available - falling back to unfiltered.")
            res = await _async_execute(lambda: db.rpc("semantic_search",
                {"p_embedding": embedding, "p_limit": limit}).execute())
            return res.data or []
        raise


async def create_memory_session(source: str, summary: str) -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("memory_sessions").insert({
        "session_source": source, "summary": summary,
    }).execute())
    return res.data[0] if res.data else {}


async def link_memory_node(node_id: str, session_id: str):
    db = get_db()
    await _async_execute(lambda: db.table("memory_node_origins").insert({
        "node_id": node_id, "session_id": session_id,
    }).execute())


async def get_memory_nodes(limit: int = 20) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.table("nodes").select(
        "id, title, body, confidence, created_at, source_ref"
    ).eq("type", "memory").eq("status", "active").order("created_at", desc=True).limit(limit).execute())
    return res.data or []


async def get_pending_review(limit: int = 20) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.table("nodes").select(
        "id, title, type, body, source, created_at"
    ).eq("status", "draft").order("created_at", desc=True).limit(limit).execute())
    return res.data or []


async def log_ingestion(data: dict) -> dict:
    db = get_db()
    res = await _async_execute(lambda: db.table("ingestion_log").insert(data).execute())
    return res.data[0] if res.data else {}


async def get_ingestion_log(limit: int = 20) -> list[dict]:
    db = get_db()
    res = await _async_execute(lambda: db.table("ingestion_log").select("*").order(
        "ingested_at", desc=True).limit(limit).execute())
    return res.data or []


async def get_failed_ingestions_since(since_timestamp: float) -> list[dict]:
    from datetime import datetime, timezone
    db = get_db()
    since_dt = datetime.fromtimestamp(since_timestamp, tz=timezone.utc).isoformat()
    res = await _async_execute(lambda: db.table("ingestion_log").select("*").eq(
        "status", "failed").gte("ingested_at", since_dt).order("ingested_at", desc=True).limit(50).execute())
    return res.data or []


async def count_nodes(status: str = "active") -> int:
    db = get_db()
    res = await _async_execute(lambda: db.table("nodes").select("id", count="exact").eq("status", status).execute())
    return res.count or 0


async def ping() -> bool:
    try:
        db = get_db()
        await _async_execute(lambda: db.table("nodes").select("id").limit(1).execute())
        return True
    except Exception:
        return False
