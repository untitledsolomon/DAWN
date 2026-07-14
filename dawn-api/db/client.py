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
                      tag: Optional[str] = None, limit: int = 50, offset: int = 0,
                      source_ref: Optional[str] = None) -> list[dict]:
    db = get_db()
    q = db.table("nodes").select(
        "id, title, type, body, status, source, source_ref, confidence, created_at, updated_at, node_tags(tags(name))"
    ).eq("status", status).order("created_at", desc=True).limit(limit).offset(offset)
    if node_type:
        q = q.eq("type", node_type)
    if source_ref:
        q = q.eq("source_ref", source_ref)
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


async def update_tag_description(name: str, description: str) -> dict:
    db = get_db()
    res = await _async_execute(
        lambda: db.table("tags").update({"description": description}).eq("name", name).execute()
    )
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
    # Always send p_exclude_types explicitly (even as None) so the call
    # unambiguously matches the 5-arg fuzzy_search signature in Postgres.
    # Omitting it lets PostgREST match both the legacy 4-arg overload and
    # the 5-arg one, causing PGRST203 "could not choose the best candidate".
    params = {
        "p_query": query,
        "p_limit": limit,
        "p_threshold": threshold,
        "p_exclude_types": exclude_types,
        "p_exclude_tags": exclude_tags,
    }
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


async def count_nodes(status: str = "active", node_type: Optional[str] = None,
                       tag: Optional[str] = None) -> int:
    """Count nodes matching the given filters.

    Uses Supabase count='exact' for accurate counts. Falls back to
    client-side filtering for tag-based counts (Supabase REST limitation).
    """
    db = get_db()
    q = db.table("nodes").select("id", count="exact").eq("status", status)
    if node_type:
        q = q.eq("type", node_type)
    if tag:
        # Tag filtering requires a join — fetch IDs and filter client-side
        res = await _async_execute(lambda: q.execute())
        total = res.count or 0
        if total == 0:
            return 0
        # Get all matching IDs to filter by tag
        ids_res = await _async_execute(lambda: (
            db.table("nodes").select("id").eq("status", status)
            .execute()
        ))
        all_ids = [n["id"] for n in (ids_res.data or [])]
        if not all_ids:
            return 0
        # Get node IDs that have the given tag
        tag_res = await _async_execute(lambda: (
            db.table("node_tags")
            .select("node_id, tags!inner(name)")
            .eq("tags.name", tag)
            .in_("node_id", all_ids)
            .execute()
        ))
        return len(tag_res.data or [])
    res = await _async_execute(lambda: q.execute())
    return res.count or 0


async def ping() -> bool:
    try:
        db = get_db()
        await _async_execute(lambda: db.table("nodes").select("id").limit(1).execute())
        return True
    except Exception:
        return False


async def create_artifact(
    session_id: str,
    type: str,
    title: str,
    description: Optional[str] = None,
    spec: Optional[dict] = None,
    code: Optional[str] = None,
    prompt: Optional[str] = None,
    metadata: Optional[dict] = None,
    url: Optional[str] = None,
    data_summary: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Shared insert path for the `artifacts` table — used by routers/artifacts.py's
    POST / (user-facing CRUD) and by routers/agent.py (when the create_chart tool
    hands back a spec that needs persisting). Keeping this here rather than
    duplicating the insert logic in both callers.
    """
    db = get_db()
    data: dict = {"session_id": session_id, "type": type, "title": title}
    if description:
        data["description"] = description
    if spec:
        data["spec"] = spec
    if code:
        data["code"] = code
    if prompt:
        data["prompt"] = prompt
    if metadata:
        data["metadata"] = metadata
    if url:
        data["url"] = url
    if data_summary:
        data["data_summary"] = data_summary
    if tags:
        data["tags"] = tags

    res = await _async_execute(lambda: db.table("artifacts").insert(data).execute())
    return res.data[0] if res.data else {}


# ─────────────────────────────────────────────
# NEW: In-memory query cache
# ─────────────────────────────────────────────
_query_cache: dict = {}
_cache_ttl: int = 300  # 5 minutes default

def _cache_key(query_type: str, **params) -> str:
    import hashlib
    raw = f"{query_type}:{json.dumps(params, sort_keys=True, default=str)}"
    return hashlib.md5(raw.encode()).hexdigest()

def _cache_get(key: str):
    import time
    entry = _query_cache.get(key)
    if entry and time.time() - entry["ts"] < _cache_ttl:
        return entry["data"]
    if entry:
        del _query_cache[key]
    return None

def _cache_set(key: str, data):
    import time
    _query_cache[key] = {"data": data, "ts": time.time()}

def cache_clear():
    _query_cache.clear()

def cache_stats() -> dict:
    return {"size": len(_query_cache), "ttl_seconds": _cache_ttl}

# ─────────────────────────────────────────────
# NEW: Unified search_all (1 RPC instead of 4-8)
# ─────────────────────────────────────────────

async def rpc_search_all(
    query: str,
    limit: int = 5,
    threshold: float = 0.2,
    exclude_types: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    include_memories: bool = True,
    embedding: Optional[list[float]] = None,
    use_cache: bool = True,
) -> dict:
    """Unified search: fuzzy + semantic + memory in one DB call.
    
    Uses in-memory cache for repeat queries. Falls back to individual
    RPC calls if search_all isn't available yet.
    """
    db = get_db()
    
    cache_key = _cache_key("search_all", query=query, limit=limit, 
                           threshold=threshold, include_memories=include_memories)
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    
    params = {
        "p_query": query,
        "p_limit": limit,
        "p_threshold": threshold,
        "p_include_memories": include_memories,
    }
    if exclude_types:
        params["p_exclude_types"] = exclude_types
    if exclude_tags:
        params["p_exclude_tags"] = exclude_tags
    if embedding:
        params["p_embedding"] = embedding
    
    try:
        res = await _async_execute(lambda: db.rpc("search_all", params).execute())
        result = res.data if res.data else {}
        if use_cache:
            _cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.warning(f"search_all RPC failed ({e}), falling back to individual searches")
        # Fallback: do individual searches
        result = {"nodes_fuzzy": [], "nodes_semantic": [], "memories": []}
        
        fuzzy = await rpc_fuzzy_search(query, limit, threshold, exclude_types, exclude_tags)
        result["nodes_fuzzy"] = fuzzy
        
        if embedding:
            semantic = await rpc_semantic_search(embedding, limit, exclude_types, exclude_tags)
            result["nodes_semantic"] = semantic
        
        if include_memories:
            mem = await rpc_fuzzy_search_memories(query, limit, threshold)
            result["memories"] = mem
        
        if use_cache:
            _cache_set(cache_key, result)
        return result

# ─────────────────────────────────────────────
# NEW: Memory CRUD
# ─────────────────────────────────────────────

async def create_memory(
    title: str,
    body: Optional[str] = None,
    fact_type: str = "preference",
    confidence: float = 0.7,
    source: str = "conversation",
    source_ref: Optional[str] = None,
    tags: Optional[list[str]] = None,
    embedding: Optional[list[float]] = None,
) -> dict:
    """Create a memory in the dedicated memories table.
    
    Auto-promotion to 'active' happens via DB trigger when confidence >= 0.8.
    """
    db = get_db()
    data = {
        "title": title,
        "fact_type": fact_type,
        "confidence": confidence,
        "source": source,
        "status": "draft",
    }
    if body:
        data["body"] = body
    if source_ref:
        data["source_ref"] = source_ref
    if tags:
        data["tags"] = tags
    if embedding:
        data["embedding"] = embedding
    
    res = await _async_execute(lambda: db.table("memories").insert(data).execute())
    return res.data[0] if res.data else {}

async def create_memories_batch(rows: list[dict], batch_size: int = 50) -> list[dict]:
    """Batch insert memories."""
    if not rows:
        return []
    db = get_db()
    created = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        res = await _async_execute(lambda b=batch: db.table("memories").insert(b).execute())
        created.extend(res.data or [])
    return created

async def update_memory(memory_id: str, data: dict) -> dict:
    """Update a memory by ID."""
    db = get_db()
    res = await _async_execute(
        lambda: db.table("memories").update(data).eq("id", memory_id).execute()
    )
    return res.data[0] if res.data else {}

async def get_memory_by_id(memory_id: str) -> Optional[dict]:
    """Get a single memory by ID."""
    db = get_db()
    res = await _async_execute(
        lambda: db.table("memories").select("*").eq("id", memory_id).limit(1).execute()
    )
    return res.data[0] if res.data else None

async def get_active_memories(limit: int = 50, offset: int = 0) -> list[dict]:
    """Get active memories, most recently accessed first."""
    db = get_db()
    res = await _async_execute(
        lambda: db.table("memories")
        .select("*")
        .eq("status", "active")
        .order("last_accessed", desc=True)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    return res.data or []

async def get_draft_memories(limit: int = 50) -> list[dict]:
    """Get draft (unreviewed) memories."""
    db = get_db()
    res = await _async_execute(
        lambda: db.table("memories")
        .select("*")
        .eq("status", "draft")
        .order("confidence", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []

# ─────────────────────────────────────────────
# NEW: Memory search functions
# ─────────────────────────────────────────────

async def rpc_fuzzy_search_memories(
    query: str, limit: int = 5, threshold: float = 0.2
) -> list[dict]:
    """Fuzzy search the memories table."""
    db = get_db()
    try:
        res = await _async_execute(
            lambda: db.rpc("fuzzy_search_memories", {
                "p_query": query, "p_limit": limit, "p_threshold": threshold
            }).execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning(f"fuzzy_search_memories RPC failed: {e}")
        return []

async def rpc_semantic_search_memories(
    embedding: list[float], limit: int = 5
) -> list[dict]:
    """Semantic search the memories table."""
    db = get_db()
    try:
        res = await _async_execute(
            lambda: db.rpc("semantic_search_memories", {
                "p_embedding": embedding, "p_limit": limit
            }).execute()
        )
        return res.data or []
    except Exception as e:
        logger.warning(f"semantic_search_memories RPC failed: {e}")
        return []

async def rpc_memory_search(
    query: str, limit: int = 5, threshold: float = 0.2,
    embedding: Optional[list[float]] = None
) -> list[dict]:
    """Search memories: fuzzy first, fall back to semantic if empty."""
    results = await rpc_fuzzy_search_memories(query, limit, threshold)
    if not results and embedding:
        results = await rpc_semantic_search_memories(embedding, limit)
    return results

# ─────────────────────────────────────────────
# NEW: Memory maintenance
# ─────────────────────────────────────────────

async def update_memory_embeddings(
    memory_id_to_embedding: dict, batch_size: int = 50
) -> int:
    """Update embeddings for memories."""
    if not memory_id_to_embedding:
        return 0
    db = get_db()
    updated = 0
    items = list(memory_id_to_embedding.items())
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        for mem_id, embedding in batch:
            if embedding is None:
                continue
            try:
                await _async_execute(
                    lambda mid=mem_id, emb=embedding: (
                        db.table("memories").update({"embedding": emb}).eq("id", mid).execute()
                    )
                )
                updated += 1
            except Exception as e:
                logger.error(f"Failed to write embedding for memory {mem_id}: {e}")
    return updated

async def consolidate_memories() -> dict:
    """Run memory consolidation (merge duplicates)."""
    db = get_db()
    try:
        res = await _async_execute(lambda: db.rpc("consolidate_memories").execute())
        return res.data if res.data else {}
    except Exception as e:
        logger.warning(f"consolidate_memories failed: {e}")
        return {}

async def decay_memories(days: int = 30, factor: float = 0.05) -> int:
    """Decay confidence of old, unaccessed memories."""
    db = get_db()
    try:
        res = await _async_execute(
            lambda: db.rpc("decay_memory_confidence", {
                "p_days_threshold": days, "p_decay_factor": factor
            }).execute()
        )
        return res.data if res.data else 0
    except Exception as e:
        logger.warning(f"decay_memory_confidence failed: {e}")
        return 0
