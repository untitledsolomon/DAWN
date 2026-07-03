"""
Embedding generation for semantic search.

Uses sentence-transformers' all-MiniLM-L6-v2 (384-dim), matching the
VECTOR(384) column defined in the schema and what semantic_search()
expects. This is a separate lightweight model from the chat LLM in
llm/engine.py — embeddings don't need DeepSeek/local-llama at all, and
running them locally avoids paying per-token API costs for something
that's cheap to run on CPU.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

_model = None


def get_embedding_model():
    """Lazy-load the sentence-transformers model as a singleton."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _model


def embed_text(text: str) -> Optional[list[float]]:
    """
    Embed a single piece of text. Returns None (rather than raising) on
    empty input or model failure, so callers can skip that node's
    embedding without crashing an entire batch ingest over one bad chunk.
    """
    text = (text or "").strip()
    if not text:
        return None
    try:
        model = get_embedding_model()
        vec = model.encode(text, show_progress_bar=False)
        return vec.tolist()
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return None


def embed_texts_batch(texts: list[str], batch_size: int = 64) -> list[Optional[list[float]]]:
    """
    Embed many texts at once. Batched through the model itself (not just
    chunked for DB writes) since encoding many short strings together is
    far more efficient on CPU than one-at-a-time — this matters directly
    for ingest throughput on a repo with hundreds of code-file nodes or a
    book with thousands of paragraph chunks.

    Returns a list the same length as `texts`, with None in place of any
    empty/failed entries so positions stay aligned with the caller's node
    list.
    """
    if not texts:
        return []

    # Track which indices actually have content — encoding empty strings
    # wastes model calls and sentence-transformers handles them oddly.
    indices_to_embed = [i for i, t in enumerate(texts) if (t or "").strip()]
    if not indices_to_embed:
        return [None] * len(texts)

    results: list[Optional[list[float]]] = [None] * len(texts)

    try:
        model = get_embedding_model()
        to_embed = [texts[i].strip() for i in indices_to_embed]
        vectors = model.encode(
            to_embed,
            batch_size=batch_size,
            show_progress_bar=False,
        )
        for idx, vec in zip(indices_to_embed, vectors):
            results[idx] = vec.tolist()
    except Exception as e:
        logger.error(f"Batch embedding failed for {len(texts)} texts: {e}")
        # Leave results as all-None; caller proceeds without embeddings
        # rather than failing the whole ingest over the embedding step.

    return results


def embed_node_text(title: str, body: str, max_chars: int = 2000) -> str:
    """
    Build the text that actually gets embedded for a node. Title is
    prepended since it often carries the most semantic signal (e.g. a
    file path or a section heading) and short bodies alone can be too
    thin for the model to place well in vector space.
    """
    combined = f"{title}\n\n{body}" if title else body
    return combined[:max_chars]
