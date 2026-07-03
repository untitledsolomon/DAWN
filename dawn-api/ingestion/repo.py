"""
Repo ingestion: reads a local git repo and creates nodes for it.
- One node for the repo itself
- One node per directory, recursively (linked via part_of to its parent dir)
- One node per source/text file (chunked if large), linked to its directory
- README.md summarised into the repo node body
"""
import os
import re
import logging
import db.client as db
from llm.engine import get_engine

logger = logging.getLogger(__name__)

# Extensions read as text/code content. Extend as your stack grows.
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".hpp", ".rb", ".php", ".sh", ".md", ".txt", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sql", ".html", ".css", ".scss",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".hpp", ".rb", ".php", ".sh", ".sql",
}

SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", "venv", "env", ".venv",
    "dist", "build", ".next", "target", ".idea", ".vscode", "coverage",
}

MAX_FILE_BYTES = 500_000  # skip absurdly large files (binaries, lockfiles, minified bundles)
MAX_REPO_FILES = 20_000   # hard cap on files processed per ingest_repo call, see truncated flag in return value
_REPO_WRITE_BATCH = 200


async def ingest_repo(repo_path: str, repo_name: str, tags: list[str] = []) -> dict:
    nodes_created = 0
    edges_created = 0
    nodes_archived = 0

    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
            all_tags.append(tag)
        tag_ids.append(tag["id"])

    # "code" tag distinguishes source files from prose/docs within a repo.
    # (node_type has no 'code' value in the DB enum — only concept/entity/
    # process/fact/memory/document — so this has to be a tag, not a type.)
    code_tag = next((t for t in all_tags if t["name"] == "code"), None)
    if not code_tag:
        code_tag = await db.create_tag("code", "Source code file, as opposed to prose/docs")
        all_tags.append(code_tag)
    code_tag_id = code_tag["id"]

    # Dedup: if this repo_path was ingested before, archive (and rename
    # out of the way, see archive_nodes_batch) its prior nodes first, so
    # re-running ingestion doesn't collide with the LOWER(title) unique
    # index or leave two overlapping copies of the same repo in the graph.
    prior = await db.get_nodes_by_source_ref_prefix(repo_path)
    if prior:
        await db.archive_nodes_batch([(n["id"], n["title"]) for n in prior])
        nodes_archived = len(prior)

    # README -> repo node body summary
    readme_body = ""
    for fname in ["README.md", "README.txt", "readme.md"]:
        readme_path = os.path.join(repo_path, fname)
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            readme_body = await _summarise_readme(raw, repo_name)
            break

    repo_node = await db.create_node({
        "title": repo_name,
        "type": "entity",
        "body": readme_body or f"Git repository: {repo_name}",
        "status": "active",
        "source": "repo",
        "source_ref": repo_path,
        "confidence": 0.9,
    })
    nodes_created += 1
    if tag_ids:
        await db.attach_tags_batch([repo_node["id"]], tag_ids)

    dir_node_ids = {repo_path: repo_node["id"]}

    # Batched write buffer shared across the whole walk. Rows carry
    # parallel metadata (parent path, whether it's a dir, whether it's
    # code) since we don't have DB ids until after insert.
    pending_rows: list[dict] = []
    pending_meta: list[dict] = []

    async def flush():
        nonlocal nodes_created, edges_created, pending_rows, pending_meta
        if not pending_rows:
            return
        created = await db.create_nodes_batch(pending_rows)
        nodes_created += len(created)

        edge_rows = []
        tagged_node_ids = []       # gets repo-level tags
        code_node_ids = []         # additionally gets the "code" tag
        for node, meta in zip(created, pending_meta):
            if not node.get("id"):
                continue
            tagged_node_ids.append(node["id"])
            if meta["is_dir"]:
                dir_node_ids[meta["fs_path"]] = node["id"]
            elif meta.get("is_code"):
                code_node_ids.append(node["id"])
            parent_id = dir_node_ids.get(meta["parent_path"], repo_node["id"])
            edge_rows.append({
                "from_node": node["id"],
                "to_node": parent_id,
                "relation": "part_of",
                "source": "repo",
            })

        if edge_rows:
            created_edges = await db.create_edges_batch(edge_rows)
            edges_created += len(created_edges)

        if tag_ids and tagged_node_ids:
            await db.attach_tags_batch(tagged_node_ids, tag_ids)
        if code_node_ids:
            await db.attach_tags_batch(code_node_ids, [code_tag_id])

        # Only embed file nodes, not directory placeholders — "Directory
        # in DAWN: dawn-api/routers/" carries no semantic content worth
        # a vector, and skipping them roughly halves embedding work on a
        # typical repo (dir count vs file count).
        file_nodes = [
            node for node, meta in zip(created, pending_meta)
            if node.get("id") and not meta["is_dir"]
        ]
        if file_nodes:
            await _embed_and_store(file_nodes)

        pending_rows = []
        pending_meta = []

    file_count = 0
    skipped_large = 0

    for root, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))

        if root != repo_path:
            rel_root = os.path.relpath(root, repo_path)
            parent_dir = os.path.dirname(root)
            pending_rows.append({
                "title": f"{repo_name}/{rel_root}",
                "type": "entity",
                "body": f"Directory in {repo_name}: {rel_root}/",
                "status": "active",
                "source": "repo",
                "source_ref": root,
                "confidence": 0.8,
            })
            pending_meta.append({"parent_path": parent_dir, "is_dir": True, "fs_path": root})

            # Directory nodes must exist (and be registered in dir_node_ids)
            # before files inside them, or deeper subdirs, can resolve
            # their parent correctly — flush now.
            await flush()

        for fname in sorted(filenames):
            if file_count >= MAX_REPO_FILES:
                logger.warning(
                    f"ingest_repo: hit MAX_REPO_FILES={MAX_REPO_FILES} limit for "
                    f"{repo_name}, stopping early. Consider narrowing repo_path "
                    f"or raising the limit if this repo is intentionally huge."
                )
                await flush()
                return {
                    "nodes_created": nodes_created,
                    "edges_created": edges_created,
                    "nodes_archived": nodes_archived,
                    "truncated": True,
                    "files_processed": file_count,
                }

            if fname.startswith("."):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in TEXT_EXTENSIONS:
                continue

            fpath = os.path.join(root, fname)
            try:
                fsize = os.path.getsize(fpath)
                if fsize > MAX_FILE_BYTES:
                    skipped_large += 1
                    continue
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except (OSError, PermissionError):
                continue

            if not content.strip():
                continue

            file_count += 1
            rel_path = os.path.relpath(fpath, repo_path)
            is_code = ext in CODE_EXTENSIONS
            chunks = list(_iter_chunks(content, max_chars=1500))

            for i, chunk in enumerate(chunks):
                title = f"{repo_name}/{rel_path}" if i == 0 else f"{repo_name}/{rel_path} (part {i + 1})"
                pending_rows.append({
                    "title": title[:200],
                    "type": "document",
                    "body": chunk,
                    "status": "active",
                    "source": "repo",
                    "source_ref": fpath,
                    "confidence": 0.85,
                })
                pending_meta.append({
                    "parent_path": root, "is_dir": False, "fs_path": fpath, "is_code": is_code,
                })

                if len(pending_rows) >= _REPO_WRITE_BATCH:
                    await flush()

    await flush()

    if skipped_large:
        logger.info(f"ingest_repo: skipped {skipped_large} file(s) over MAX_FILE_BYTES in {repo_name}")

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "nodes_archived": nodes_archived,
        "truncated": False,
        "files_processed": file_count,
    }


async def _embed_and_store(created_nodes: list[dict]):
    """
    Compute and write embeddings for a freshly-created batch of nodes.
    Failures here are logged and swallowed, never raised — a node
    missing its embedding is a degraded-search problem, not a reason to
    fail an otherwise-successful ingest. This is what makes newly
    ingested content actually reachable via semantic_search, which was
    previously silent-dead since nothing ever populated `embedding`.

    Wrapped defensively end-to-end: a missing dependency (pytesseract,
    sentence-transformers, or this module itself not yet deployed), a
    model load failure, or any other embedding-path error must degrade
    to "no embeddings this run" rather than crashing the whole ingest —
    losing a 300-page PDF's worth of already-extracted nodes over an
    embedding step failing is strictly worse than just skipping vectors.
    """
    try:
        from llm.embeddings import embed_texts_batch, embed_node_text
    except ImportError as e:
        logger.warning(
            f"Skipping embeddings — llm.embeddings unavailable ({e}). "
            f"Nodes were still created successfully; they just won't be "
            f"reachable via semantic_search until this is fixed and "
            f"re-embedded."
        )
        return

    valid = [n for n in created_nodes if n.get("id")]
    if not valid:
        return

    try:
        texts = [embed_node_text(n.get("title", ""), n.get("body", "")) for n in valid]
        vectors = embed_texts_batch(texts)

        node_id_to_embedding = {
            n["id"]: vec for n, vec in zip(valid, vectors) if vec is not None
        }
        if node_id_to_embedding:
            await db.update_node_embeddings(node_id_to_embedding)
    except Exception as e:
        logger.error(f"Embedding step failed for a batch of {len(valid)} node(s), continuing without them: {e}")


async def ingest_document(
    title: str,
    content: str,
    source_ref: str = "",
    tags: list[str] = [],
) -> dict:
    """Chunk a text document into nodes and write them in batches."""
    chunk_iter = _iter_chunks(content, max_chars=1500)
    return await _ingest_chunk_stream(
        title, chunk_iter, source_ref, tags,
        empty_fallback_body=content[:300] if content else "(no extractable content)",
    )


async def ingest_document_stream(
    title: str,
    text_pieces,
    source_ref: str = "",
    tags: list[str] = [],
) -> dict:
    """
    Like ingest_document, but takes an iterable of text pieces (e.g. one
    string per PDF page from iter_pdf_pages) instead of one big string.

    This is the entry point for arbitrarily large documents: at no point
    is the full document held in memory as a single string — pieces are
    re-chunked to a consistent size on the fly and flushed in batches.
    Memory use stays bounded by a handful of pages/chunks at a time,
    regardless of whether the source document is 50 pages or 50,000.
    """
    def _regrouped_chunks():
        buf = ""
        for piece in text_pieces:
            piece = (piece or "").strip()
            if not piece:
                continue
            if len(buf) + len(piece) + 2 <= 1500:
                buf += ("\n\n" if buf else "") + piece
            else:
                if buf:
                    yield buf
                # a single page/piece bigger than max_chars: hard-split it
                if len(piece) > 1500:
                    for i in range(0, len(piece), 1500):
                        yield piece[i:i + 1500]
                    buf = ""
                else:
                    buf = piece
        if buf:
            yield buf

    return await _ingest_chunk_stream(
        title, _regrouped_chunks(), source_ref, tags,
        empty_fallback_body="(no extractable content)",
    )


async def _ingest_chunk_stream(
    title: str,
    chunk_iter,
    source_ref: str,
    tags: list[str],
    empty_fallback_body: str,
) -> dict:
    """
    Shared batching core: consumes an iterator of text chunks and writes
    them as document nodes in bounded-size batches.

    Scales to very large documents by:
    - Never materialising more than `_WRITE_BATCH` chunks in memory before
      flushing them to the DB.
    - Writing nodes via a single multi-row insert per batch instead of one
      request per chunk.
    - Attaching tags per-batch instead of per-node.

    Dedups by archiving+renaming any prior nodes for this exact source_ref
    before writing new ones (see db.archive_nodes_batch for why renaming,
    not just status change, is required).
    """
    nodes_archived = 0
    if source_ref:
        prior = await db.get_nodes_by_source_ref_prefix(source_ref)
        if prior:
            await db.archive_nodes_batch([(n["id"], n["title"]) for n in prior])
            nodes_archived = len(prior)

    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
            all_tags.append(tag)
        tag_ids.append(tag["id"])

    nodes_created = 0
    edges_created = 0
    parent_id: str | None = None
    _WRITE_BATCH = 200

    pending_rows: list[dict] = []
    part_num = 1

    async def flush():
        nonlocal nodes_created, edges_created, parent_id, pending_rows
        if not pending_rows:
            return
        created_nodes = await db.create_nodes_batch(pending_rows)
        nodes_created += len(created_nodes)

        node_ids = [n["id"] for n in created_nodes if n.get("id")]

        if parent_id is None and node_ids:
            parent_id = node_ids[0]
            edge_targets = node_ids[1:]
        else:
            edge_targets = node_ids

        if edge_targets and parent_id:
            edge_rows = [
                {"from_node": nid, "to_node": parent_id, "relation": "part_of", "source": "document"}
                for nid in edge_targets
            ]
            created_edges = await db.create_edges_batch(edge_rows)
            edges_created += len(created_edges)

        if tag_ids and node_ids:
            await db.attach_tags_batch(node_ids, tag_ids)

        # Embeddings computed per-batch, after ids exist, so semantic
        # search has data for newly-ingested content instead of leaving
        # `embedding` null forever (which is what happened before this
        # was wired up — semantic_search silently excludes null rows).
        if node_ids:
            await _embed_and_store(created_nodes)

        pending_rows = []

    empty = True
    for chunk in chunk_iter:
        empty = False
        node_title = title if part_num == 1 else f"{title} (part {part_num})"
        pending_rows.append({
            "title": node_title[:200],
            "type": "document",
            "body": chunk,
            "status": "active",
            "source": "document",
            "source_ref": source_ref,
            "confidence": 0.85,
        })
        part_num += 1

        if len(pending_rows) >= _WRITE_BATCH:
            await flush()

    if empty:
        pending_rows.append({
            "title": title,
            "type": "document",
            "body": empty_fallback_body,
            "status": "active",
            "source": "document",
            "source_ref": source_ref,
            "confidence": 0.3,
        })

    await flush()

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "nodes_archived": nodes_archived,
    }


async def ingest_sections(
    title: str,
    sections: list[dict],   # [{"title": str, "body": str}]
    source_ref: str = "",
    tags: list[str] = [],
    node_type: str = "document",
) -> dict:
    """
    Ingest pre-structured sections (from MD headings, docx headings, EPUB
    chapters, CSV rows, XLSX rows). Creates one parent node and one child
    node per section, linked via part_of, written in batches so this
    scales to large spreadsheets/ebooks with thousands of sections.
    """
    nodes_created = 0
    edges_created = 0
    nodes_archived = 0
    _WRITE_BATCH = 200

    # Dedup: archive any prior ingest of this exact source before writing
    # new nodes, so re-uploading the same file doesn't collide with the
    # LOWER(title) unique index or leave stale duplicates in the graph.
    if source_ref:
        prior = await db.get_nodes_by_source_ref_prefix(source_ref)
        if prior:
            await db.archive_nodes_batch([(n["id"], n["title"]) for n in prior])
            nodes_archived = len(prior)

    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
            all_tags.append(tag)
        tag_ids.append(tag["id"])

    parent = await db.create_node({
        "title": title,
        "type": node_type,
        "body": f"{len(sections)} sections from {source_ref or title}",
        "status": "active",
        "source": "document",
        "source_ref": source_ref,
        "confidence": 0.85,
    })
    nodes_created += 1
    if tag_ids:
        await db.attach_tags_batch([parent["id"]], tag_ids)

    pending_rows: list[dict] = []

    async def flush():
        nonlocal nodes_created, edges_created, pending_rows
        if not pending_rows:
            return
        created = await db.create_nodes_batch(pending_rows)
        nodes_created += len(created)
        node_ids = [n["id"] for n in created if n.get("id")]

        edge_rows = [
            {"from_node": nid, "to_node": parent["id"], "relation": "part_of", "source": "document"}
            for nid in node_ids
        ]
        if edge_rows:
            created_edges = await db.create_edges_batch(edge_rows)
            edges_created += len(created_edges)

        if tag_ids and node_ids:
            await db.attach_tags_batch(node_ids, tag_ids)

        if node_ids:
            await _embed_and_store(created)

        pending_rows = []

    for section in sections:
        body = (section.get("body") or "").strip()
        if not body:
            continue

        raw_title = f"{title} — {section['title']}"[:200]
        pending_rows.append({
            "title": raw_title,
            "type": node_type,
            "body": body[:1000],
            "status": "active",
            "source": "document",
            "source_ref": source_ref,
            "confidence": 0.85,
        })

        if len(pending_rows) >= _WRITE_BATCH:
            await flush()

    await flush()

    return {
        "nodes_created": nodes_created,
        "edges_created": edges_created,
        "nodes_archived": nodes_archived,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Non-streaming variant kept for callers that want a plain list."""
    return list(_iter_chunks(text, max_chars))


def _iter_chunks(text: str, max_chars: int = 1500):
    """
    Yield paragraph-grouped chunks one at a time instead of building the
    full chunk list up front. Falls back to a hard character split for
    any single paragraph that's already larger than max_chars on its own
    (e.g. a wall-of-text page with no blank lines) so one huge paragraph
    can't produce one huge node or block the generator.
    """
    text = text.strip()
    if not text:
        return

    current = ""
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue

        if len(para) > max_chars:
            if current:
                yield current
                current = ""
            for i in range(0, len(para), max_chars):
                yield para[i:i + max_chars]
            continue

        if len(current) + len(para) + 2 <= max_chars:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                yield current
            current = para

    if current:
        yield current


async def _summarise_readme(readme: str, repo_name: str) -> str:
    """Use the LLM to produce a short summary of a README."""
    try:
        engine = get_engine()
        prompt = f"Summarise this README for a knowledge graph node in 2-3 sentences. Be specific about what the project does and its tech stack.\n\nREADME:\n{readme[:3000]}"
        summary = await engine.complete([{"role": "user", "content": prompt}])
        return summary.strip()
    except Exception:
        # Fallback: first 300 chars of README
        return readme[:300].strip()
