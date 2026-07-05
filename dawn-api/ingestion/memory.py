"""
Memory ingestion: extracts durable facts from a conversation transcript
and stores them as draft memory nodes for review.

LLM calls are optional — if the LLM is unavailable, memory ingestion
gracefully degrades to creating a session with no facts rather than
failing entirely.
"""
import db.client as db
from llm.engine import get_engine
from llm.tools import extract_memory_facts
import logging

logger = logging.getLogger(__name__)


async def ingest_memory(conversation: str, session_source: str = "manual") -> dict:
    nodes_created = 0

    # Try to extract facts via LLM, but don't fail if LLM is down
    facts = []
    try:
        engine = get_engine()
        facts = await extract_memory_facts(conversation, engine.complete)
    except Exception as e:
        logger.warning(f"Memory fact extraction skipped (LLM unavailable): {e}")

    if not facts:
        # Still create a session record so we know the conversation happened
        session = await db.create_memory_session(
            source=session_source,
            summary=conversation[:200],
        )
        return {"nodes_created": 0, "session_id": session.get("id")}

    session = await db.create_memory_session(
        source=session_source,
        summary=conversation[:200],
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

    return {"nodes_created": nodes_created, "session_id": session.get("id")}
