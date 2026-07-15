"""
Graph retrieval pipeline.
Two-stage: entity extraction → graph traversal → context assembly.
No LLM needed for retrieval — that's the whole point.
"""
from dataclasses import dataclass, field
from typing import Optional
import re
import db.client as db
from llm.embeddings import embed_text

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


async def build_context(query: str, max_nodes: int = 10, include_code: bool = False, web_search_enabled: bool = False) -> ContextResult:
    """
    Main retrieval pipeline.
    1. Try fuzzy search on full query + key terms (code-tagged nodes
       excluded by default — see include_code)
    2. If fuzzy search finds nothing, fall back to semantic (embedding)
       search on the raw query
    3. Traverse from best-matching entry nodes
    4. For table-type nodes, automatically include their full-data children
       regardless of max_nodes limit
    5. Return assembled context string + metadata

    include_code=False by default: once repo ingestion has been used a
    few times, code-chunk nodes vastly outnumber concept/entity/fact
    nodes in the graph, and trigram similarity on source code text
    competes directly with — and often crowds out — the conceptual
    nodes a normal chat query is actually looking for. Set
    include_code=True for queries that are explicitly about the
    codebase (e.g. routed there by intent detection upstream).

    web_search_enabled=False by default: when True, adds a note to the
    context telling the LLM it can use web search for supplementary info.
    """
    tool_calls: list[ToolCall] = []
    node_ids: list[str] = []
    node_titles: list[str] = []
    context_parts: list[str] = []
    seen_ids: set[str] = set()

    exclude_tags = None if include_code else ["code"]

    # ── Stage 1: Find entry nodes via fuzzy search ────────────────────────────────
    candidates = extract_key_terms(query)
    entry_nodes: list[dict] = []

    for term in candidates[:4]:  # Don't hammer the DB — first 4 candidates
        results = await db.rpc_fuzzy_search(term, limit=3, threshold=0.15, exclude_tags=exclude_tags)
        tc = ToolCall(name="fuzzy_search", args={"query": term}, result_count=len(results))
        tool_calls.append(tc)

        for node in results:
            if node["id"] not in seen_ids:
                entry_nodes.append(node)
                seen_ids.add(node["id"])

        if len(entry_nodes) >= 3:
            break  # Good enough entry points found

    # ── Stage 1b: Semantic fallback if fuzzy search found nothing ─────────────────
    # Trigram similarity misses paraphrases and conceptually-related but
    # differently-worded content ("bot keeps losing money" vs a node
    # titled "Sharpe ratio degradation") — this is exactly what
    # embeddings exist to catch, and until now nothing called it.
    if not entry_nodes:
        embedding = embed_text(query)
        if embedding:
            results = await db.rpc_semantic_search(embedding, limit=5, exclude_tags=exclude_tags)
            tc = ToolCall(name="semantic_search", args={"query": query}, result_count=len(results))
            tool_calls.append(tc)
            for node in results:
                if node["id"] not in seen_ids:
                    entry_nodes.append(node)
                    seen_ids.add(node["id"])

    if not entry_nodes:
        # If web search is enabled, still return empty context but note it
        if web_search_enabled:
            return ContextResult(
                context="[No relevant knowledge graph nodes found. Use web search to answer this query.]",
                tool_calls=tool_calls,
                node_ids=[],
                node_titles=[],
            )
        return ContextResult(
            context="",
            tool_calls=tool_calls,
            node_ids=[],
            node_titles=[],
        )

    # ── Stage 2: Traverse from entry nodes ────────────────────────────────────────
    # Track how many nodes we've added so we can dynamically increase the limit
    # for table-type parents
    nodes_added = 0
    # Dynamic max_nodes: start with the default, increase for table nodes
    effective_max = max_nodes

    for entry in entry_nodes[:3]:  # Top 3 entry points
        node_id = entry["id"]
        node_ids.append(node_id)
        node_titles.append(entry["title"])
        nodes_added += 1

        if entry.get("body"):
            context_parts.append(f"**{entry['title']}** ({entry.get('type', 'node')}):\n{entry['body']}")

        # Check if this is a table-type node — if so, we need its children
        is_table_node = entry.get("type") == "table"

        # Traverse outward
        traversal = await db.rpc_traverse(node_id, max_depth=2)
        tc = ToolCall(
            name="traverse",
            args={"node_id": node_id, "depth": 2},
            result_count=len(traversal),
        )
        tool_calls.append(tc)

        # For table nodes, we want ALL children — dynamically increase limit
        if is_table_node:
            # Count how many children we'll need
            child_count = sum(1 for t in traversal if t.get("via_relation") == "part_of"
                              and t.get("parent_id") == node_id)
            # Ensure we have room for all children + some margin
            needed = nodes_added + child_count + 2  # +2 for other entry nodes
            if needed > effective_max:
                effective_max = needed

        for t_node in traversal:
            if t_node["id"] not in seen_ids and nodes_added < effective_max:
                seen_ids.add(t_node["id"])
                node_ids.append(t_node["id"])
                node_titles.append(t_node["title"])
                nodes_added += 1

                if t_node.get("body"):
                    depth_indent = "  " * t_node.get("depth", 1)
                    relation = t_node.get("via_relation", "related")
                    context_parts.append(
                        f"{depth_indent}→ **{t_node['title']}** [{relation}]:\n{depth_indent}  {t_node['body']}"
                    )

    context = "\n\n".join(context_parts)

    # Add web search note if enabled
    if web_search_enabled:
        context += (
            "\n\n[Web Search Available] If the information above is insufficient "
            "or outdated, you can use the web_search tool to find current information."
        )

    return ContextResult(
        context=context,
        tool_calls=tool_calls,
        node_ids=node_ids,
        node_titles=node_titles,
    )


async def build_code_context(query: str, max_nodes: int = 8) -> ContextResult:
    """
    Retrieval pipeline scoped specifically to code-tagged nodes — for
    queries that are explicitly about the codebase itself (e.g. "where
    do we handle Supabase polling retries", "show me the MT5 EA connection
    logic"). Uses fuzzy_search_code (requires migration 002) rather than
    build_context's default code-exclusion behavior.
    """
    tool_calls: list[ToolCall] = []
    node_ids: list[str] = []
    node_titles: list[str] = []
    context_parts: list[str] = []
    seen_ids: set[str] = set()

    candidates = extract_key_terms(query)
    for term in candidates[:4]:
        results = await db.rpc_fuzzy_search_code(term, limit=max_nodes)
        tc = ToolCall(name="fuzzy_search_code", args={"query": term}, result_count=len(results))
        tool_calls.append(tc)

        for node in results:
            if node["id"] not in seen_ids and len(node_ids) < max_nodes:
                seen_ids.add(node["id"])
                node_ids.append(node["id"])
                node_titles.append(node["title"])
                ref = f" ({node['source_ref']})" if node.get("source_ref") else ""
                if node.get("body"):
                    context_parts.append(f"**{node['title']}**{ref}:\n```\n{node['body']}\n```")

        if len(node_ids) >= max_nodes:
            break

    return ContextResult(
        context="\n\n".join(context_parts),
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
    Runs as a background task — output goes to memories table as status='draft'.

    v40.0: Increased context window from 3000 to 8000 chars so the LLM
    sees more of the conversation before extracting facts.
    """
    prompt = f"""Extract durable facts from this conversation worth remembering long-term about Solomon, his projects, or decisions made.

Rules:
- Only facts that won't change week-to-week
- Specific and concrete, not vague observations
- Maximum 5 facts
- Return JSON array: [{{"title": "short title", "body": "fact in one sentence", "tags": ["tag1"]}}]
- Return ONLY the JSON array, no other text

Conversation:
{conversation[-8000:]}
"""

    try:
        raw = await llm_complete_fn([{"role": "user", "content": prompt}])
        # Strip markdown fences if present
        raw = raw.strip().strip("```json").strip("```").strip()
        import json
        facts = json.loads(raw)
        return facts if isinstance(facts, list) else []
    except Exception:
        return []


async def extract_error_pattern(
    user_message: str,
    assistant_response: str,
    llm_complete_fn,
) -> Optional[dict]:
    """
    After a chat exchange, check if DAWN made a mistake worth learning from.
    Returns a dict with pattern, context, and resolution if an error is detected.
    """
    prompt = f"""Analyze this conversation exchange and determine if DAWN (the AI assistant) made a mistake, gave incorrect information, or could have answered better.

If a mistake or error pattern is detected, return a JSON object describing it.
If no error was made, return an empty JSON object.

Rules:
- Be honest — only flag real errors, not minor phrasing differences
- Focus on factual errors, incorrect code, wrong assumptions
- Return JSON: {{"pattern": "short description of the error pattern", "context": "what the user was asking about", "resolution": "how to correctly answer this"}}
- Return ONLY the JSON object, no other text

User message: {user_message[:1000]}
DAWN response: {assistant_response[:2000]}
"""

    try:
        raw = await llm_complete_fn([{"role": "user", "content": prompt}])
        raw = raw.strip().strip("```json").strip("```").strip()
        import json
        result = json.loads(raw)
        if result and result.get("pattern"):
            return result
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# NEW: Memory storage and retrieval
# ─────────────────────────────────────────────────────────────────────────────

async def store_memory_facts(
    facts: list[dict],
    source: str = "conversation",
    source_ref: Optional[str] = None,
) -> list[dict]:
    """Store extracted facts into the dedicated memories table.
    
    v40.0: Now generates embeddings for each fact so semantic search works.
    Previously, memories were stored without embeddings — fuzzy search only.
    
    Each fact dict should have: title, body (optional), tags (optional).
    The DB trigger auto-promotes high-confidence facts to 'active'.
    """
    if not facts:
        return []
    
    rows = []
    for fact in facts:
        title = fact.get("title", fact.get("content", "Untitled memory"))
        body = fact.get("body", fact.get("content", ""))
        
        # Generate embedding for semantic search
        text_to_embed = f"{title}\n{body}" if body else title
        embedding = embed_text(text_to_embed)
        
        row = {
            "title": title,
            "body": body,
            "fact_type": fact.get("fact_type", "fact"),
            "confidence": fact.get("confidence", 0.7),
            "source": source,
            "status": "draft",
        }
        if embedding:
            row["embedding"] = embedding
        if source_ref:
            row["source_ref"] = source_ref
        if fact.get("tags"):
            row["tags"] = fact["tags"]
        rows.append(row)
    
    return await db.create_memories_batch(rows)


async def extract_and_store_memory(
    conversation: str,
    llm_complete_fn,
    source_ref: Optional[str] = None,
) -> list[dict]:
    """Full pipeline: extract facts from conversation, store in memories table.
    
    v40.0: Now checks for duplicate/similar memories before storing.
    If a very similar memory already exists, it boosts the existing one's
    confidence rather than creating a duplicate. This prevents the same
    fact from being stored 20 times across different conversations.
    """
    facts = await extract_memory_facts(conversation, llm_complete_fn)
    if not facts:
        return []
    
    # Classify each fact
    for fact in facts:
        body_lower = fact.get("body", "").lower()
        if any(w in body_lower for w in ["prefer", "like", "dislike", "favorite", "love", "hate"]):
            fact["fact_type"] = "preference"
        elif any(w in body_lower for w in ["decided", "chose", "going with", "will use"]):
            fact["fact_type"] = "decision"
        elif any(w in body_lower for w in ["always", "never", "every time", "pattern"]):
            fact["fact_type"] = "pattern"
        else:
            fact["fact_type"] = "fact"
    
    # Check for duplicates before storing
    stored = []
    for fact in facts:
        # Search for similar existing memories
        title = fact.get("title", "")
        body = fact.get("body", "")
        search_text = f"{title} {body}"
        
        existing = await db.rpc_fuzzy_search_memories(search_text, limit=3, threshold=0.4)
        
        if existing:
            # Found a similar memory — boost its confidence instead of duplicating
            for match in existing:
                if match.get("confidence", 0) < 0.9:
                    new_confidence = min(match.get("confidence", 0.7) + 0.1, 0.95)
                    await db.update_memory(match["id"], {"confidence": new_confidence})
                    stored.append(match)
                    break
        else:
            # No duplicate found — store as new
            result = await store_memory_facts([fact], source="conversation", source_ref=source_ref)
            stored.extend(result)
    
    return stored


async def load_memory_context(
    query: str,
    max_memories: int = 5,
    threshold: float = 0.2,
) -> str:
    """Load relevant memories for a query using unified search.
    
    v40.0: Falls back to semantic search if fuzzy search finds nothing.
    Previously, only fuzzy search was used — this missed memories that
    were semantically related but phrased differently.
    
    Returns a formatted string of memory context, or empty string if none found.
    """
    # Try fuzzy search first
    memories = await db.rpc_fuzzy_search_memories(query, limit=max_memories, threshold=threshold)
    
    # Fall back to semantic search if fuzzy found nothing
    if not memories:
        embedding = embed_text(query)
        if embedding:
            memories = await db.rpc_semantic_search_memories(embedding, limit=max_memories)
    
    if not memories:
        return ""
    
    parts = []
    for mem in memories:
        title = mem.get("title", "Untitled")
        body = mem.get("body", "")
        fact_type = mem.get("fact_type", "fact")
        confidence = mem.get("confidence", 0.0)
        
        if body:
            parts.append(f"[Memory: {fact_type} (confidence: {confidence:.2f})] {title}: {body}")
        else:
            parts.append(f"[Memory: {fact_type} (confidence: {confidence:.2f})] {title}")
    
    return "\n".join(parts)
