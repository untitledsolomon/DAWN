"""
Memory tool — explicit store/recall/list for DAWN's persistent memory system.

This gives the agent (me) a way to explicitly say "I'll remember that"
and actually do it, rather than relying solely on the background
extraction pipeline. It also lets me recall stored memories on demand.

v40.0: New tool. Previously, memories were only extracted in the background
by routers/chat.py — the agent had no way to explicitly store or query them.
"""
from typing import Optional
import logging
from tools.base import BaseTool, ToolResult
from llm.embeddings import embed_text
import db.client as db

logger = logging.getLogger(__name__)


class MemoryStoreTool(BaseTool):
    """Explicitly store a memory fact. Use this when the user tells you
    something they want you to remember — a preference, a decision, a
    personal fact, or anything else worth persisting across conversations.
    
    Memories stored via this tool get high confidence (0.85) and are
    immediately available in future conversations.
    """
    
    name = "store_memory"
    description = "Store a fact about the user (Solomon) that should be remembered across conversations. Use when the user explicitly tells you something to remember, or when you learn a durable fact about their preferences, projects, or decisions."
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the memory (e.g. 'Preferred stack for web apps')"
            },
            "body": {
                "type": "string",
                "description": "The fact to remember — specific and concrete"
            },
            "fact_type": {
                "type": "string",
                "enum": ["preference", "decision", "pattern", "fact"],
                "description": "Type of memory. 'preference' for likes/dislikes, 'decision' for choices made, 'pattern' for recurring behaviors, 'fact' for general knowledge"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags to categorize this memory (e.g. ['tech-stack', 'trading'])"
            }
        },
        "required": ["title", "body"]
    }
    
    async def run(self, title: str, body: str, fact_type: str = "fact", tags: Optional[list[str]] = None) -> ToolResult:
        try:
            # Generate embedding for semantic search
            text_to_embed = f"{title}\n{body}"
            embedding = embed_text(text_to_embed)
            
            memory = await db.create_memory(
                title=title,
                body=body,
                fact_type=fact_type,
                confidence=0.85,  # High confidence — user explicitly told us
                source="agent",
                tags=tags or [],
                embedding=embedding,
            )
            
            if memory and memory.get("id"):
                return ToolResult(
                    success=True,
                    output={
                        "id": memory["id"],
                        "title": title,
                        "fact_type": fact_type,
                        "status": memory.get("status", "draft"),
                        "message": f"Stored memory: {title}",
                    },
                    metadata={"memory_id": memory.get("id")},
                )
            else:
                return ToolResult(
                    success=False,
                    error="Failed to store memory — database returned no record",
                )
        except Exception as e:
            logger.exception(f"MemoryStoreTool failed: {e}")
            return ToolResult(success=False, error=str(e))


class MemoryRecallTool(BaseTool):
    """Search stored memories. Use this when you need to recall what you
    know about the user, their preferences, past decisions, or any other
    persistent information.
    """
    
    name = "recall_memory"
    description = "Search stored memories about the user. Use when you need to recall preferences, past decisions, personal facts, or anything else that might have been stored across conversations."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for — e.g. 'preferred tech stack', 'trading strategy', 'favorite tools'"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of memories to return (default: 5)",
                "default": 5
            }
        },
        "required": ["query"]
    }
    
    async def run(self, query: str, limit: int = 5) -> ToolResult:
        try:
            # Try fuzzy search first
            memories = await db.rpc_fuzzy_search_memories(query, limit=limit, threshold=0.2)
            
            # Fall back to semantic search if fuzzy found nothing
            if not memories:
                embedding = embed_text(query)
                if embedding:
                    memories = await db.rpc_semantic_search_memories(embedding, limit=limit)
            
            if not memories:
                return ToolResult(
                    success=True,
                    output={"memories": [], "message": "No memories found for that query"},
                )
            
            formatted = []
            for mem in memories:
                formatted.append({
                    "id": mem.get("id"),
                    "title": mem.get("title"),
                    "body": mem.get("body"),
                    "fact_type": mem.get("fact_type"),
                    "confidence": mem.get("confidence"),
                    "status": mem.get("status"),
                    "created_at": mem.get("created_at"),
                })
            
            return ToolResult(
                success=True,
                output={
                    "memories": formatted,
                    "count": len(formatted),
                    "message": f"Found {len(formatted)} memory/memories",
                },
            )
        except Exception as e:
            logger.exception(f"MemoryRecallTool failed: {e}")
            return ToolResult(success=False, error=str(e))


class MemoryListTool(BaseTool):
    """List all active memories. Use this to get an overview of everything
    DAWN remembers about the user.
    """
    
    name = "list_memories"
    description = "List all active stored memories about the user. Use to get an overview of what DAWN currently remembers."
    input_schema = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of memories to return (default: 20)",
                "default": 20
            },
            "status": {
                "type": "string",
                "enum": ["active", "draft", "all"],
                "description": "Filter by status (default: active)",
                "default": "active"
            }
        }
    }
    
    async def run(self, limit: int = 20, status: str = "active") -> ToolResult:
        try:
            if status == "all":
                # Get both active and draft
                active = await db.get_active_memories(limit=limit)
                draft = await db.get_draft_memories(limit=limit)
                memories = active + draft
            elif status == "draft":
                memories = await db.get_draft_memories(limit=limit)
            else:
                memories = await db.get_active_memories(limit=limit)
            
            formatted = []
            for mem in memories:
                formatted.append({
                    "id": mem.get("id"),
                    "title": mem.get("title"),
                    "body": mem.get("body"),
                    "fact_type": mem.get("fact_type"),
                    "confidence": mem.get("confidence"),
                    "status": mem.get("status"),
                    "created_at": mem.get("created_at"),
                })
            
            return ToolResult(
                success=True,
                output={
                    "memories": formatted,
                    "count": len(formatted),
                    "message": f"Found {len(formatted)} memory/memories (status: {status})",
                },
            )
        except Exception as e:
            logger.exception(f"MemoryListTool failed: {e}")
            return ToolResult(success=False, error=str(e))
