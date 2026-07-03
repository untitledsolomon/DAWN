from supabase import create_client, Client
from config import settings
from typing import Optional
import json
import logging

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


# ── Node CRUD ─────────────────────────────────────────────────────────────────

async def create_node(data: dict) -> dict:
    db = get_db()
    res = db.table("nodes").insert(data).execute()
    return res.data[0] if res.data else {}


async def create_nodes_batch(rows: list[dict], batch_size: int = 200) -> list[dict]:
    """
    Insert many node rows in chunked multi-row inserts instead of one
    request per row. Returns all created rows (with generated ids) in
    the same order they were submitted. Used by large ingests (big PDFs,
    repos with many files) to avoid tens of thousands of individual
    round trips to Supabase.
    """
    if not rows:
        return []
    db = get_db()
    created: list[dict] = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        res = db.table("nodes").insert(batch).execute()
        created.extend(res.data or [])
    return created


async def get_node_by_id(node_id: str) -> Optional[dict]:
    db = get_db()
    res = db.rpc("get_node", {"p_id": node_id}).execute()
    return res.data


async def update_node(node_id: str, data: dict) -> dict:
    db = get_db()
    res = db.table("nodes").update(data).eq("id", node_id).execute()
    return res.data[0] if res.data else {}


async def delete_node(node_id: str) -> bool:
    db = get_db()
    db.table("nodes").delete().eq("id", node_id).execute()
    return True


async def list_nodes(
    status: str = "active",
    node_type: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    db = get_db()
    q = db.table("nodes").select(
        "id, title, type, body, status, source, confidence, created_at, updated_at, node_tags(tags(name))"
    ).eq("status", status).order("created_at", desc=True).limit(limit).offset(offset)

    if node_type:
        q = q.eq("type", node_type)

    res = q.execute()
    nodes = res.data or []

    # Flatten tags
    for node in nodes:
        raw_tags = node.pop("node_tags", []) or []
        node["tags"] = [t["tags"]["name"] for t in raw_tags if t.get("tags")]

    # Filter by tag after fetch (Supabase join filter is awkward)
    if tag:
        nodes = [n for n in nodes if tag in n.get("tags", [])]

    return nodes


# ── Edge CRUD ─────────────────────────────────────────────────────────────────

async def create_edge(data: dict) -> dict:
    db = get_db()
    res = db.table("edges").insert(data).execute()
    return res.data[0] if res.data else {}


async def create_edges_batch(rows: list[dict], batch_size: int = 200) -> list[dict]:
    if not rows:
        return []
    db = get_db()
    created: list[dict] = []
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        res = db.table("edges").insert(batch).execute()
        created.extend(res.data or [])
    return created


async def delete_edge(edge_id: str) -> bool:
    db = get_db()
    db.table("edges").delete().eq("id", edge_id).execute()
    return True


async def get_nodes_by_source_ref_prefix(prefix: str, limit: int = 5000) -> list[dict]:
    """
    Find existing active/stale nodes whose source_ref starts with the given
    prefix (e.g. a repo path or a file path). Used to detect and clean up
    prior ingests of the same source before re-ingesting — see
    archive_nodes_batch for why archiving alone isn't enough.
    """
    db = get_db()
    res = (
        db.table("nodes")
        .select("id, title, source_ref, status")
        .like("source_ref", f"{prefix}%")
        .in_("status", ["active", "stale"])
        .limit(limit)
        .execute()
    )
    return res.data or []


async def archive_nodes_batch(node_ids_and_titles: list[tuple], batch_size: int = 200):
    """
    Archive prior nodes from a re-ingested source and rename them out of
    the way. Renaming is required, not just cosmetic: idx_nodes_title_lower
    is a UNIQUE index on LOWER(title) covering ALL rows regardless of
    status, so an archived node still blocks a new insert of the same
    title. We prefix the old title with an "archived:" + short id marker
    so it's clearly identifiable and out of collision range, while the
    row (and any edges pointing at it) stays intact for history.

    Args:
        node_ids_and_titles: list of (node_id, old_title) tuples.
    """
    if not node_ids_and_titles:
        return
    db = get_db()
    for i in range(0, len(node_ids_and_titles), batch_size):
        batch = node_ids_and_titles[i:i + batch_size]
        for node_id, old_title in batch:
            new_title = f"[archived {node_id[:8]}] {old_title}"[:250]
            db.table("nodes").update({
                "status": "archived",
                "title": new_title,
            }).eq("id", node_id).execute()


async def update_node_embeddings(node_id_to_embedding: dict, batch_size: int = 50) -> int:
    """
    Write embeddings back onto existing nodes by id. Supabase's Python
    client doesn't support a true multi-row "update different values per
    row" in one call, so this is one request per node — but it's kept
    to a modest batch_size and always called from background ingestion
    tasks, never inline on the request path, so it doesn't block anything
    user-facing. Returns count of successful updates.
    """
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
                db.table("nodes").update({"embedding": embedding}).eq("id", node_id).execute()
                updated += 1
            except Exception as e:
                logger.error(f"Failed to write embedding for node {node_id}: {e}")
    return updated


# ── Tag helpers ───────────────────────────────────────────────────────────────

async def get_all_tags() -> list[dict]:
    db = get_db()
    res = db.table("tags").select("*").order("name").execute()
    return res.data or []


async def create_tag(name: str, description: str = "") -> dict:
    db = get_db()
    res = db.table("tags").insert({"name": name, "description": description}).execute()
    return res.data[0] if res.data else {}


async def attach_tag(node_id: str, tag_id: str):
    db = get_db()
    db.table("node_tags").upsert({"node_id": node_id, "tag_id": tag_id}).execute()


async def attach_tags_batch(node_ids: list[str], tag_ids: list[str], batch_size: int = 500):
    """Attach the same set of tags to many nodes in chunked multi-row upserts."""
    if not node_ids or not tag_ids:
        return
    db = get_db()
    rows = [{"node_id": nid, "tag_id": tid} for nid in node_ids for tid in tag_ids]
    for i in range(0, len(rows), batch_size):
        db.table("node_tags").upsert(rows[i:i + batch_size]).execute()


# ── Graph tool functions (call Postgres RPC) ──────────────────────────────────

async def rpc_get_node(node_id: str) -> Optional[dict]:
    db = get_db()
    res = db.rpc("get_node", {"p_id": node_id}).execute()
    return res.data


async def rpc_traverse(
    start_id: str,
    relations: Optional[list[str]] = None,
    max_depth: int = 2,
) -> list[dict]:
    db = get_db()
    params = {"p_start_id": start_id, "p_max_depth": max_depth}
    if relations:
        params["p_relations"] = relations
    res = db.rpc("traverse", params).execute()
    return res.data or []


async def rpc_fuzzy_search(
    query: str,
    limit: int = 5,
    threshold: float = 0.2,
    exclude_types: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
) -> list[dict]:
    """
    exclude_types/exclude_tags require migration 002 (adds p_exclude_types/
    p_exclude_tags params to the fuzzy_search RPC). If that migration
    hasn't been applied yet, Postgres will raise an unknown-parameter
    error — caught here and retried with the original signature, so this
    doesn't hard-break search on an un-migrated database. Once migrated,
    the retry path is never hit.
    """
    db = get_db()
    params = {"p_query": query, "p_limit": limit, "p_threshold": threshold}
    if exclude_types:
        params["p_exclude_types"] = exclude_types
    if exclude_tags:
        params["p_exclude_tags"] = exclude_tags

    try:
        res = db.rpc("fuzzy_search", params).execute()
        return res.data or []
    except Exception as e:
        if (exclude_types or exclude_tags) and "p_exclude" in str(e):
            logger.warning(
                "fuzzy_search called with exclude filters but migration 002 "
                "doesn't appear to be applied — falling back to unfiltered search."
            )
            res = db.rpc(
                "fuzzy_search",
                {"p_query": query, "p_limit": limit, "p_threshold": threshold},
            ).execute()
            return res.data or []
        raise


async def rpc_fuzzy_search_code(query: str, limit: int = 5, threshold: float = 0.2) -> list[dict]:
    """Search only nodes tagged 'code' — requires migration 002 (fuzzy_search_code RPC)."""
    db = get_db()
    res = db.rpc(
        "fuzzy_search_code",
        {"p_query": query, "p_limit": limit, "p_threshold": threshold},
    ).execute()
    return res.data or []


async def rpc_search_tags(tag_name: str) -> list[dict]:
    db = get_db()
    res = db.rpc("search_tags", {"p_tag_name": tag_name}).execute()
    return res.data or []


async def rpc_semantic_search(
    embedding: list[float],
    limit: int = 5,
    exclude_types: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
) -> list[dict]:
    """See rpc_fuzzy_search docstring re: migration 002 fallback behavior."""
    db = get_db()
    params = {"p_embedding": embedding, "p_limit": limit}
    if exclude_types:
        params["p_exclude_types"] = exclude_types
    if exclude_tags:
        params["p_exclude_tags"] = exclude_tags

    try:
        res = db.rpc("semantic_search", params).execute()
        return res.data or []
    except Exception as e:
        if (exclude_types or exclude_tags) and "p_exclude" in str(e):
            logger.warning(
                "semantic_search called with exclude filters but migration 002 "
                "doesn't appear to be applied — falling back to unfiltered search."
            )
            res = db.rpc("semantic_search", {"p_embedding": embedding, "p_limit": limit}).execute()
            return res.data or []
        raise


# ── Memory ────────────────────────────────────────────────────────────────────

async def create_memory_session(source: str, summary: str) -> dict:
    db = get_db()
    res = db.table("memory_sessions").insert({
        "session_source": source,
        "summary": summary,
    }).execute()
    return res.data[0] if res.data else {}


async def link_memory_node(node_id: str, session_id: str):
    db = get_db()
    db.table("memory_node_origins").insert({
        "node_id": node_id,
        "session_id": session_id,
    }).execute()


async def get_memory_nodes(limit: int = 20) -> list[dict]:
    db = get_db()
    res = db.table("nodes").select(
        "id, title, body, confidence, created_at, source_ref"
    ).eq("type", "memory").eq("status", "active").order(
        "created_at", desc=True
    ).limit(limit).execute()
    return res.data or []


async def get_pending_review(limit: int = 20) -> list[dict]:
    db = get_db()
    res = db.table("nodes").select(
        "id, title, type, body, source, created_at"
    ).eq("status", "draft").order("created_at", desc=True).limit(limit).execute()
    return res.data or []


# ── Ingestion log ─────────────────────────────────────────────────────────────

async def log_ingestion(data: dict) -> dict:
    db = get_db()
    res = db.table("ingestion_log").insert(data).execute()
    return res.data[0] if res.data else {}


async def get_ingestion_log(limit: int = 20) -> list[dict]:
    db = get_db()
    res = db.table("ingestion_log").select("*").order(
        "ingested_at", desc=True
    ).limit(limit).execute()
    return res.data or []
