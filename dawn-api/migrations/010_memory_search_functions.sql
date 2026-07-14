-- ============================================================
-- MIGRATION 010: Memory search functions (fallback for search_all)
-- ============================================================
-- These are the individual memory search functions used as fallback
-- when the unified search_all RPC isn't available (e.g. during
-- migration rollout). Also useful for direct memory-only queries.
-- ============================================================

-- Fuzzy search on memories table
CREATE OR REPLACE FUNCTION fuzzy_search_memories(
  p_query     TEXT,
  p_limit     INT DEFAULT 5,
  p_threshold FLOAT DEFAULT 0.2
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'id', m.id,
    'title', m.title,
    'body', m.body,
    'confidence', m.confidence,
    'fact_type', m.fact_type,
    'tags', m.tags,
    'similarity', GREATEST(
      similarity(LOWER(m.title), LOWER(p_query)),
      similarity(LOWER(m.body),  LOWER(p_query))
    )
  ) ORDER BY GREATEST(
    similarity(LOWER(m.title), LOWER(p_query)),
    similarity(LOWER(m.body),  LOWER(p_query))
  ) DESC) INTO result
  FROM memories m
  WHERE
    m.status = 'active'
    AND GREATEST(
      similarity(LOWER(m.title), LOWER(p_query)),
      similarity(LOWER(m.body),  LOWER(p_query))
    ) > p_threshold
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- Semantic search on memories table
CREATE OR REPLACE FUNCTION semantic_search_memories(
  p_embedding VECTOR(384),
  p_limit     INT DEFAULT 5
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'id', m.id,
    'title', m.title,
    'body', m.body,
    'confidence', m.confidence,
    'fact_type', m.fact_type,
    'tags', m.tags,
    'distance', m.embedding <=> p_embedding
  ) ORDER BY m.embedding <=> p_embedding) INTO result
  FROM memories m
  WHERE m.status = 'active'
    AND m.embedding IS NOT NULL
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- Count memories by status (for diagnostics)
CREATE OR REPLACE FUNCTION count_memories(p_status TEXT DEFAULT 'active')
RETURNS INT AS $$
DECLARE
  total INT;
BEGIN
  SELECT COUNT(*) INTO total FROM memories WHERE status = p_status;
  RETURN total;
END;
$$ LANGUAGE plpgsql;


-- Get recent memories (for diagnostics / review)
CREATE OR REPLACE FUNCTION get_recent_memories(
  p_limit INT DEFAULT 20,
  p_status TEXT DEFAULT 'active'
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'id', m.id,
    'title', m.title,
    'body', m.body,
    'confidence', m.confidence,
    'fact_type', m.fact_type,
    'status', m.status,
    'tags', m.tags,
    'access_count', m.access_count,
    'created_at', m.created_at
  ) ORDER BY m.created_at DESC) INTO result
  FROM memories m
  WHERE m.status = p_status
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- Force PostgREST to reload its schema cache
NOTIFY pgrst, 'reload schema';
