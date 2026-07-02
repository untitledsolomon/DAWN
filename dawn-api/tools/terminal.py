"""
Graph retrieval pipeline.
Two-stage: entity extraction → graph traversal → context assembly.
No LLM needed for retrieval — that's the whole point.
"""
from dataclasses import dataclass, field
from typing import Optional
import re
import db.client as db

# Words not worth searching for
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "and", "or", "but", "if", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "how", "what", "where", "when", "who", "why", "which",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it", "they",
    "this", "that", "these", "those", "there", "here",
    "make", "build", "create", "tell", "get", "give", "find", "show",
    "help", "want", "need", "like", "just", "also", "so", "then", "than",
}


@dataclass
class ToolCall:
    name: str
    args: dict
    result_count: int = 0


@dataclass
class ContextResult:
    context: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    node_titles: list[str] = field(default_factory=list)


def extract_key_terms(query: str) -> list[str]:
    """Pull meaningful terms out of a query for graph lookup."""
    # Lowercase, remove punctuation
    cleaned = re.sub(r"[^\w\s]", " ", query.lower())
    words = cleaned.split()

    # Filter stopwords and short words
    terms = [w for w in words if w not in STOPWORDS and len(w) > 2]

    # Also include multi-word phrases (2-gram) — useful for "jet engine", "trading bot" etc.
    bigrams = [f"{terms[i]} {terms[i+1]}" for i in range(len(terms) - 1)]

    # Full query as first attempt, then bigrams, then unigrams
    candidates = [query] + bigrams + terms
    return candidates


async def build_context(query: str, max_nodes: int = 10) -> ContextResult:
    """
    Main retrieval pipeline.
    1. Try fuzzy search on full query + key terms
    2. Traverse from best-matching entry nodes
    3. Return assembled context string + metadata
    """
    tool_calls: list[ToolCall] = []
    node_ids: list[str] = []
    node_titles: list[str] = []
    context_parts: list[str] = []
    seen_ids: set[str] = set()

    # ── Stage 1: Find entry nodes ─────────────────────────────────────────────
    candidates = extract_key_terms(query)
    entry_nodes: list[dict] = []

    for term in candidates[:4]:  # Don't hammer the DB — first 4 candidates
        results = await db.rpc_fuzzy_search(term, limit=3, threshold=0.15)
        tc = ToolCall(name="fuzzy_search", args={"query": term}, result_count=len(results))
        tool_calls.append(tc)

        for node in results:
            if node["id"] not in seen_ids:
                entry_nodes.append(node)
                seen_ids.add(node["id"])

        if len(entry_nodes) >= 3:
            break  # Good enough entry points found

    if not entry_nodes:
        return ContextResult(
            context="",
            tool_calls=tool_calls,
            node_ids=[],
            node_titles=[],
        )

    # ── Stage 2: Traverse from entry nodes ───────────────────────────────────
    for entry in entry_nodes[:3]:  # Top 3 entry points
        node_id = entry["id"]
        node_ids.append(node_id)
        node_titles.append(entry["title"])

        if entry.get("body"):
            context_parts.append(f"**{entry['title']}** ({entry.get('type', 'node')}):\n{entry['body']}")

        # Traverse outward
        traversal = await db.rpc_traverse(node_id, max_depth=2)
        tc = ToolCall(
            name="traverse",
            args={"node_id": node_id, "depth": 2},
            result_count=len(traversal),
        )
        tool_calls.append(tc)

        for t_node in traversal:
            if t_node["id"] not in seen_ids and len(node_ids) < max_nodes:
                seen_ids.add(t_node["id"])
                node_ids.append(t_node["id"])
                node_titles.append(t_node["title"])

                if t_node.get("body"):
                    depth_indent = "  " * t_node.get("depth", 1)
                    relation = t_node.get("via_relation", "related")
                    context_parts.append(
                        f"{depth_indent}→ **{t_node['title']}** [{relation}]:\n{depth_indent}  {t_node['body']}"
                    )

    context = "\n\n".join(context_parts)
    return ContextResult(
        context=context,
        tool_calls=tool_calls,
        node_ids=node_ids,
        node_titles=node_titles,
    )


async def extract_memory_facts(
    conversation: str,
    llm_complete_fn,
) -> list[dict]:
    """
    After a chat session, extract durable facts worth storing as memory nodes.
    Runs as a background task — output goes to nodes table as status='draft'.
    """
    prompt = f"""Extract durable facts from this conversation worth remembering long-term about Solomon, his projects, or decisions made.

Rules:
- Only facts that won't change week-to-week
- Specific and concrete, not vague observations
- Maximum 5 facts
- Return JSON array: [{{"title": "short title", "body": "fact in one sentence", "tags": ["tag1"]}}]
- Return ONLY the JSON array, no other text

Conversation:
{conversation[-3000:]}"""

    try:
        raw = await llm_complete_fn([{"role": "user", "content": prompt}])
        # Strip markdown fences if present
        raw = raw.strip().strip("```json").strip("```").strip()
        import json
        facts = json.loads(raw)
        return facts if isinstance(facts, list) else []
    except Exception:
        return []
