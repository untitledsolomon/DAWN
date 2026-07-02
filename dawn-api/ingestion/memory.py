"""
Memory ingestion: extracts durable facts from a conversation transcript
and stores them as draft memory nodes for review.
"""
import db.client as db
from llm.engine import get_engine
from llm.tools import extract_memory_facts


async def ingest_memory(conversation: str, session_source: str = "manual") -> dict:
    engine = get_engine()
    nodes_created = 0

    facts = await extract_memory_facts(conversation, engine.complete)
    if not facts:
        return {"nodes_created": 0}

    session = await db.create_memory_session(
        source=session_source,
        summary=conversation[:100],
    )

    all_tags = await db.get_all_tags()

    for fact in facts[:5]:
        node = await db.create_node({
            "title": fact.get("title", "Memory"),
            "type": "memory",
            "body": fact.get("body", ""),
            "status": "draft",          # Always draft — Solomon reviews before activating
            "source": "conversation",
            "source_ref": session_source,
            "confidence": 0.7,
        })

        if node.get("id"):
            nodes_created += 1
            if session.get("id"):
                await db.link_memory_node(node["id"], session["id"])

            for tag_name in fact.get("tags", []):
                tag = next((t for t in all_tags if t["name"] == tag_name), None)
                if not tag:
                    tag = await db.create_tag(tag_name)
                    all_tags.append(tag)
                await db.attach_tag(node["id"], tag["id"])

    return {"nodes_created": nodes_created}
