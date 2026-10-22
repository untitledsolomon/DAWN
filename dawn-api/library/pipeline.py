"""Library pipeline — fetch → extract text → chunk → embed → write (idempotent)."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Optional

import db.client as db
from library import store
from library.chunker import chunk_text

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\\1>", re.S | re.I)


def html_to_text(raw: str) -> str:
    body = _SCRIPT_RE.sub(" ", raw)
    body = _TAG_RE.sub(" ", body)
    body = re.sub(r"\s+", " ", body)
    return body.strip()


def extract_text(content_type: str, raw: str) -> str:
    if "html" in content_type:
        return html_to_text(raw)
    return raw


async def _queue_job(kind: str, params: dict, requested_by: str, document_id: Optional[str] = None) -> Optional[dict]:
    supabase = db.get_db()
    res = await db._async_execute(
        lambda: supabase.table("ingest_jobs").insert({
            "kind": kind, "params": params, "requested_by": requested_by,
            "document_id": document_id, "status": "queued",
        }).execute()
    )
    return (res.data or [{}])[0] if res.data else None


async def _embed_off_loop(texts: list[str]):
    from llm.embeddings import embed_texts_batch
    return await asyncio.get_event_loop().run_in_executor(None, embed_texts_batch, texts)


async def ingest_url(
    url: str,
    kind: str = "docs_page",
    title: Optional[str] = None,
    collection_name: Optional[str] = None,
    requested_by: str = "user",
) -> dict:
    """Fetch a URL and write it to the library. Idempotent on content hash."""
    job = await _queue_job("fetch", {"url": url, "kind": kind, "title": title}, requested_by)

    try:
        from library.fetcher import fetch, FetchError
        data = await fetch(url)
    except FetchError as e:
        supabase = db.get_db()
        await db._async_execute(
            lambda: supabase.table("ingest_jobs").update({
                "status": "failed", "error_class": getattr(e, "error_class", "fetch.blocked"),
                "error": str(e), "finished_at": "now()",
            }).eq("id", (job or {}).get("id")).execute()
        )
        return {"ok": False, "error": str(e), "error_class": getattr(e, "error_class", "fetch.blocked")}

    raw = data["bytes"].decode("utf-8", errors="replace")
    text = extract_text(data.get("content_type", ""), raw)[:400_000]
    if not text.strip():
        return {"ok": False, "error": "no readable text extracted"}

    doc_title = title or (url.rstrip("/").split("/")[-1] or url)

    # Idempotency: same content hash for this client => reuse the document.
    existing = None
    try:
        res = await db._async_execute(
            lambda: db.get_db().table("library_documents").select("id")
            .eq("content_hash", data["content_hash"]).maybe_single().execute()
        )
        existing = res.data
    except Exception:
        existing = None
    if existing:
        return {"ok": True, "document_id": existing["id"], "status": "exists"}

    doc = await store.create_document({
        "title": doc_title, "kind": kind, "source_type": "url",
        "source_url": data["final_url"], "status": "processing",
        "content_hash": data["content_hash"], "text_hash": hashlib.sha256(text.encode()).hexdigest(),
        "mime": data.get("content_type") or "", "bytes": len(data["bytes"]),
        "etag": data.get("etag"), "last_modified": data.get("last_modified"),
        "fetched_at": "now()", "metadata": {"pipeline": "v2"},
    })
    if not doc:
        return {"ok": False, "error": "could not create document row"}

    raw_chunks = chunk_text(text, title=doc_title, section_path="")
    vectors = await _embed_off_loop([c["embed_text"] for c in raw_chunks])
    for c, v in zip(raw_chunks, vectors):
        c["embedding"] = (v or [None] * 384) if v is not None else None
    for c in raw_chunks:
        c.update({"client_id": doc.get("client_id"), "document_id": doc["id"], "generation": 0})
    await store.insert_chunks(raw_chunks)

    embedded = sum(1 for c in raw_chunks if c.get("embedding"))
    status = "ready" if embedded == len(raw_chunks) else "partial"
    await store.update_document(doc["id"], {
        "status": status, "chunk_count": len(raw_chunks), "embedded_count": embedded,
        "current_generation": 0, "error": None,
    })
    await _queue_job("embed", {}, "worker", doc["id"])
    return {"ok": True, "document_id": doc["id"], "status": status, "chunks": len(raw_chunks)}


async def domain_allowed(client_id: Optional[str], host: str) -> bool:
    try:
        res = await db._async_execute(
            lambda: db.get_db().table("ingest_domain_policy").select("decision")
            .eq("host", host).maybe_single().execute()
        )
        return (res.data or {}).get("decision") == "allow"
    except Exception:
        return False
