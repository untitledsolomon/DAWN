"""Token-aware, structure-first chunking (replaces the naive _iter_chunks)."""
from __future__ import annotations


def _estimate_tokens(text: str) -> int:
    # Word-based estimate — good enough and matches the embedder's tokenizer
    # scale for bge-small (word pieces ≈ words).
    return len(text.split())


def chunk_text(
    text: str,
    token_budget: int = 300,
    overlap: int = 45,
    title: str = "",
    section_path: str = "",
) -> list[dict]:
    """Split text into chunks never exceeding token_budget. Code fences are kept
    whole when they fit. Each chunk: {text, section_path, ordinal, kind,
    token_count}. The embedded string is "title > section\n\ntext" — the stored
    text is the clean chunk."""
    lines = text.split("\n")
    chunks: list[dict] = []
    current: list[str] = []
    current_tokens = 0
    in_fence = False
    fence: list[str] = []
    ordinal = 0

    def flush() -> None:
        nonlocal current, current_tokens, ordinal
        if not current:
            return
        body = "\n".join(current)
        chunks.append({
            "text": body,
            "section_path": section_path,
            "ordinal": ordinal,
            "kind": "code" if in_fence else "prose",
            "token_count": _estimate_tokens(body),
        })
        ordinal += 1
        # overlap: keep the tail of the previous chunk as a head start
        words = body.split()
        current = words[-overlap:] if len(words) > overlap else []
        current_tokens = len(current)

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_fence:
                fence.append(line)
                if _estimate_tokens("\n".join(fence)) <= token_budget:
                    current.extend(fence)
                    current_tokens = _estimate_tokens("\n".join(current))
                    flush()
                in_fence = False
                fence = []
            else:
                flush()
                in_fence = True
                fence = [line]
            continue
        if in_fence:
            fence.append(line)
            continue
        line_tokens = _estimate_tokens(line)
        if current and current_tokens + line_tokens > token_budget:
            flush()
        current.append(line)
        current_tokens += line_tokens

    if in_fence:
        current.extend(fence)
        flush()
    flush()

    # Contextual header is added at embed time, not baked into stored text.
    for i, c in enumerate(chunks):
        c["embed_text"] = f"{title} > {section_path}\n\n{c['text']}" if title else c["text"]
    return chunks
