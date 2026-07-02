from supabase import create_client, Client
from config import settings
from typing import Optional
import json

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


async def delete_edge(edge_id: str) -> bool:
    db = get_db()
    db.table("edges").delete().eq("id", edge_id).execute()
    return True


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
) -> list[dict]:
    db = get_db()
    res = db.rpc(
        "fuzzy_search",
        {"p_query": query, "p_limit": limit, "p_threshold": threshold},
    ).execute()
    return res.data or []


async def rpc_search_tags(tag_name: str) -> list[dict]:
    db = get_db()
    res = db.rpc("search_tags", {"p_tag_name": tag_name}).execute()
    return res.data or []


async def rpc_semantic_search(embedding: list[float], limit: int = 5) -> list[dict]:
    db = get_db()
    res = db.rpc(
        "semantic_search",
        {"p_embedding": embedding, "p_limit": limit},
    ).execute()
    return res.data or []


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
