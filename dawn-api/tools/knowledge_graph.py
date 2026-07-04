"""
Knowledge graph tool — lets Agent mode do what Chat mode gets for free.

Chat mode (routers/chat.py) always runs build_context() + _load_memory_context()
before every reply, so the model is automatically grounded in whatever DAWN
already knows. Agent mode (llm/agent.py) deliberately doesn't do this up
front — see build_agent_messages()'s docstring — the intent was for the
agent to pull graph/memory context on demand via a tool instead, so it
doesn't pay for a traversal on every single turn regardless of whether the
task needs it. This is that tool.

Read-only: it never writes to nodes/edges/memory_* tables itself (that
still only happens via the background _extract_and_store_memory task after
a reply). Safe to expose to every trust tier, unlike tools/database.py.
"""
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult
from llm.tools import build_context, extract_key_terms
import db.client as db

logger = logging.getLogger(__name__)


class KnowledgeGraphTool(BaseTool):
    name = "knowledge_graph"
    description = (
        "Search DAWN's knowledge graph and long-term memory before answering questions about "
        "Solomon, Regent, his projects (OMNI, DAWN itself, Sentinel, nyao_scalper, EconSim, "
        "Dominion, Mabruk Atelier, Axis, etc.), past decisions, or anything that might already "
        "be recorded rather than something you need to look up externally or ask about. Use "
        "'search' for a natural-language question — it returns assembled context from related "
        "nodes the same way plain Chat mode does automatically. Use 'recall' specifically for "
        "personal facts, preferences, and things learned from earlier conversations (memory-type "
        "nodes only). Call this before assuming you don't know something, and before doing "
        "external work (web search, file reads) that might already have a recorded answer here."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["search", "recall"],
                "description": "'search' = general knowledge-graph context; 'recall' = memory/fact/preference nodes only.",
            },
            "query": {
                "type": "string",
                "description": "Natural-language question or topic to search for.",
            },
            "max_nodes": {
                "type": "integer",
                "description": "Max nodes to pull into context for 'search'. Defaults to 10.",
            },
        },
        "required": ["operation", "query"],
    }

    async def run(
        self,
        operation: str,
        query: str,
        max_nodes: Optional[int] = None,
    ) -> ToolResult:
        try:
            if operation == "search":
                return await self._search(query, max_nodes or 10)
            elif operation == "recall":
                return await self._recall(query)
            else:
                return ToolResult(success=False, error=f"Unknown operation '{operation}'.")
        except Exception as e:
            logger.error(f"[knowledge_graph tool] {operation} failed: {e}")
            return ToolResult(success=False, error=str(e))

    async def _search(self, query: str, max_nodes: int) -> ToolResult:
        result = await build_context(query, max_nodes=max_nodes)
        if not result.context:
            return ToolResult(
                success=True,
                output="No related nodes found in the knowledge graph for this query.",
                metadata={"node_ids": [], "node_titles": []},
            )
        return ToolResult(
            success=True,
            output=result.context,
            metadata={"node_ids": result.node_ids, "node_titles": result.node_titles},
        )

    async def _recall(self, query: str) -> ToolResult:
        """Mirrors routers/chat.py's _load_memory_context, but as an
        on-demand tool call instead of something run unconditionally
        before every reply."""
        terms = extract_key_terms(query)
        memory_parts: list[str] = []
        seen: set[str] = set()

        for term in terms[:3]:
            results = await db.rpc_fuzzy_search(term, limit=3, threshold=0.2)
            for node in results:
                node_id = node.get("id")
                if node_id not in seen and node.get("type") in ("memory", "fact", "preference"):
                    seen.add(node_id)
                    if node.get("body"):
                        memory_parts.append(f"[{node['type']}] {node['title']}: {node['body']}")

        if not memory_parts:
            return ToolResult(success=True, output="No matching memories found.")

        return ToolResult(success=True, output="\n".join(memory_parts[:5]))
