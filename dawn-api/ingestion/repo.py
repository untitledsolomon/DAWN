"""
Repo ingestion: reads a local git repo and creates nodes for it.
- One node for the repo itself
- One node per top-level directory (linked via part_of)
- README.md summarised into the repo node body
"""
import os
import re
import db.client as db
from llm.engine import get_engine


async def ingest_repo(repo_path: str, repo_name: str, tags: list[str] = []) -> dict:
    nodes_created = 0
    edges_created = 0

    # Resolve all tag IDs
    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
        tag_ids.append(tag["id"])

    # Read README if present
    readme_body = ""
    for fname in ["README.md", "README.txt", "readme.md"]:
        readme_path = os.path.join(repo_path, fname)
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
            readme_body = await _summarise_readme(raw, repo_name)
            break

    # Create root repo node
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

    for tag_id in tag_ids:
        await db.attach_tag(repo_node["id"], tag_id)

    # Create nodes for top-level directories
    try:
        entries = os.listdir(repo_path)
    except PermissionError:
        entries = []

    for entry in sorted(entries):
        full_path = os.path.join(repo_path, entry)
        if not os.path.isdir(full_path) or entry.startswith("."):
            continue

        # Skip common noise dirs
        if entry in {"node_modules", "__pycache__", ".git", "venv", "env", ".venv", "dist", "build"}:
            continue

        dir_node = await db.create_node({
            "title": f"{repo_name}/{entry}",
            "type": "entity",
            "body": f"Directory in {repo_name}: {entry}/",
            "status": "active",
            "source": "repo",
            "source_ref": full_path,
            "confidence": 0.8,
        })
        nodes_created += 1

        for tag_id in tag_ids:
            await db.attach_tag(dir_node["id"], tag_id)

        edge = await db.create_edge({
            "from_node": dir_node["id"],
            "to_node": repo_node["id"],
            "relation": "part_of",
            "source": "repo",
        })
        edges_created += 1

    return {"nodes_created": nodes_created, "edges_created": edges_created}


async def ingest_document(
    title: str,
    content: str,
    source_ref: str = "",
    tags: list[str] = [],
) -> dict:
    """Chunk a text document into nodes."""
    nodes_created = 0

    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
        tag_ids.append(tag["id"])

    # Simple chunking: split on double newlines, max 500 chars per chunk
    chunks = _chunk_text(content, max_chars=500)

    # Create one parent node for the document
    parent = await db.create_node({
        "title": title,
        "type": "document",
        "body": chunks[0] if chunks else content[:300],
        "status": "active",
        "source": "document",
        "source_ref": source_ref,
        "confidence": 0.85,
    })
    nodes_created += 1

    for tag_id in tag_ids:
        await db.attach_tag(parent["id"], tag_id)

    # Create child nodes for subsequent chunks
    for i, chunk in enumerate(chunks[1:], start=2):
        child = await db.create_node({
            "title": f"{title} (part {i})",
            "type": "document",
            "body": chunk,
            "status": "active",
            "source": "document",
            "source_ref": source_ref,
            "confidence": 0.85,
        })
        nodes_created += 1

        for tag_id in tag_ids:
            await db.attach_tag(child["id"], tag_id)

        await db.create_edge({
            "from_node": child["id"],
            "to_node": parent["id"],
            "relation": "part_of",
            "source": "document",
        })

    return {"nodes_created": nodes_created, "edges_created": nodes_created - 1}


async def ingest_sections(
    title: str,
    sections: list[dict],   # [{"title": str, "body": str}]
    source_ref: str = "",
    tags: list[str] = [],
    node_type: str = "document",
) -> dict:
    """
    Ingest pre-structured sections (from MD headings, CSV rows, XLSX rows).
    Creates one parent node and one child node per section, linked via part_of.
    """
    nodes_created = 0
    edges_created = 0

    all_tags = await db.get_all_tags()
    tag_ids = []
    for tag_name in tags:
        tag = next((t for t in all_tags if t["name"] == tag_name), None)
        if not tag:
            tag = await db.create_tag(tag_name)
            all_tags.append(tag)
        tag_ids.append(tag["id"])

    # Parent node summarising the whole document/file
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
    for tag_id in tag_ids:
        await db.attach_tag(parent["id"], tag_id)

    # Child nodes — one per section
    for section in sections:
        body = section.get("body", "").strip()
        if not body:
            continue

        child = await db.create_node({
            "title": f"{title} — {section['title']}"[:200],
            "type": node_type,
            "body": body[:1000],     # cap individual node body length
            "status": "active",
            "source": "document",
            "source_ref": source_ref,
            "confidence": 0.85,
        })
        nodes_created += 1

        for tag_id in tag_ids:
            await db.attach_tag(child["id"], tag_id)

        await db.create_edge({
            "from_node": child["id"],
            "to_node": parent["id"],
            "relation": "part_of",
            "source": "document",
        })
        edges_created += 1

    return {"nodes_created": nodes_created, "edges_created": edges_created}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text.strip())
    chunks = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) < max_chars:
            current += ("\n\n" if current else "") + para
        else:
            if current:
                chunks.append(current.strip())
            current = para

    if current:
        chunks.append(current.strip())

    return chunks or [text[:max_chars]]


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
