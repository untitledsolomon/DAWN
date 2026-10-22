"""Library store — Supabase backend: documents, chunks, hybrid search, audit."""
from __future__ import annotations

import logging
import re
from typing import Optional

import db.client as db

logger = logging.getLogger(__name__)

KEYWORD_TERMS_RE = re.compile(r"[A-Za-z0-9_]+")
NIL_UUID = "00000000-0000-0000-0000-000000000000"

# Supabase's generated identity for library access (no auth header in v1).
CLIENT_IDENT = "user"


def default_client() -> str:
    return NIL_UUID


async def create_document(data: dict) -> Optional[dict]:
    data = dict(data)
    data.setdefault("client_id", default_client())
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("library_documents").insert(data).execute())
    return (res.data or [{}])[0] if res.data else None


async def get_document(doc_id: str, client_id: Optional[str] = None) -> Optional[dict]:
    supabase = db.get_db()
    q = supabase.table("library_documents").select("*").eq("id", doc_id)
    if client_id:
        q = q.eq("client_id", client_id)
    res = await db._async_execute(lambda: q.maybe_single().execute())
    return res.data if res and res.data else None


async def update_document(doc_id: str, data: dict) -> None:
    data = dict(data)
    data["updated_at"] = "now()"
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("library_documents").update(data).eq("id", doc_id).execute())


async def list_documents(client_id: Optional[str] = None, collection_id: Optional[str] = None,
                         status: Optional[str] = None, limit: int = 100) -> list[dict]:
    supabase = db.get_db()
    q = supabase.table("library_documents").select("*")
    if client_id:
        q = q.eq("client_id", client_id)
    if collection_id:
        q = q.eq("collection_id", collection_id)
    if status:
        q = q.eq("status", status)
    res = await db._async_execute(lambda: q.order("created_at", desc=True).limit(limit).execute())
    return res.data or []


async def insert_chunks(chunks: list[dict]) -> None:
    """Bulk insert chunks (with embeddings inline), batched."""
    supabase = db.get_db()
    batch = 200
    for i in range(0, len(chunks), batch):
        rows = []
        for c in chunks[i : i + batch]:
            rows.append({
                "client_id": c.get("client_id") or default_client(),
                "document_id": c["document_id"],
                "generation": c["generation"],
                "ordinal": c["ordinal"],
                "section_path": c.get("section_path"),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
                "text": c["text"],
                "kind": c.get("kind", "prose"),
                "token_count": c.get("token_count", len(c["text"].split())),
                "embedding": c.get("embedding"),
            })
        if rows:
            await db._async_execute(lambda: supabase.table("library_chunks").insert(rows).execute())


async def delete_generation(document_id: str, generation: int) -> None:
    supabase = db.get_db()
    await db._async_execute(
        lambda: supabase.table("library_chunks").delete()
        .eq("document_id", document_id).eq("generation", generation).execute()
    )


async def search_chunks(
    query: str,
    client_id: Optional[str] = None,
    embedding: Optional[list[float]] = None,
    limit: int = 6,
    collection_id: Optional[str] = None,
) -> list[dict]:
    """Hybrid retrieval: keyword (ilike) + vector, merged by RRF. Returns cited
    passages with document title, section path and source."""
    client_id = client_id or default_client()
    supabase = db.get_db()
    terms = [t.lower() for t in KEYWORD_TERMS_RE.findall(query or "") if len(t) > 2][:6]
    scores: dict[int, float] = {}
    rows: dict[int, dict] = {}

    # Keyword leg.
    if terms:
        for term in terms:
            res = await db._async_execute(
                lambda t=term: supabase.table("library_chunks").select(
                    "id, client_id, document_id, generation, section_path, page_start, page_end, text, library_documents!inner(title, source_url, status, current_generation)"
                ).eq("client_id", client_id).ilike("text", f"%{t}%").limit(100).execute()
            )
            for r in res.data or []:
                doc = r.pop("library_documents", None) or {}
                r["title"] = doc.get("title")
                r["source_url"] = doc.get("source_url")
                # only the current generation of a ready/partial doc is searchable
                if r.get("generation") != doc.get("current_generation"):
                    continue
                if doc.get("status") not in ("ready", "partial"):
                    continue
                if r["id"] in scores:
                    scores[r["id"]] += 1.0
                else:
                    scores[r["id"]] = 1.0
                    rows[r["id"]] = r

    # Vector leg.
    if embedding:
        try:
            res = await db._async_execute(
                lambda: supabase.rpc("library_embedding_search", {
                    "p_client": client_id, "p_embedding": embedding, "p_limit": limit * 2,
                }).execute()
            )
            for r in res.data or []:
                rk = r["chunk_id"]
                rows[rk] = {"id": rk, "text": r["text"], "section_path": r["section_path"],
                            "page_start": r["page_start"], "page_end": r["page_end"],
                            "title": r["title"], "source_url": r["source_url"]}
                scores[rk] = scores.get(rk, 0.0) + 2.0
        except Exception:
            logger.warning("[library] vector search unavailable (embedding index not built?)")

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    out_rows = []
    for rk, _s in ranked:
        r = rows[rk]
        pages = f"{r.get('page_start') or ''}-{r.get('page_end') or ''}".strip("-")
        out_rows.append({
            "chunk_id": rk,
            "document": r.get("title") or "",
            "section": r.get("section_path") or "",
            "pages": pages,
            "source": r.get("source_url") or "upload",
            "score": round(min(_s, 10.0) / 10.0, 4),
            "text": r.get("text") or "",
        })
    return out_rows


async def log_access(client_id: Optional[str], actor: str, action: str,
                     document_ids: Optional[list[str]] = None, query: Optional[str] = None,
                     result_count: Optional[int] = None) -> None:
    try:
        supabase = db.get_db()
        await db._async_execute(
            lambda: supabase.table("library_access_log").insert({
                "client_id": client_id or default_client(),
                "actor": actor,
                "action": action,
                "document_ids": document_ids or [],
                "query": query,
                "result_count": result_count,
            }).execute()
        )
    except Exception:
        logger.warning("[library] access log write failed")
