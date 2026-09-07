-- ============================================================
-- MIGRATION 013: Hybrid search (fuzzy + semantic merged)
-- ============================================================
-- Retrieval quality improvement. The existing fuzzy_search and
-- semantic_search are treated as separate fallbacks: fuzzy first,
-- semantic only when fuzzy finds nothing. That misses results that
-- match one signal but not the other.
--
-- hybrid_search runs BOTH searches and merges the results into a
-- single ranked list, deduplicating by node id and scoring each hit
-- by a weighted combination of trigram similarity and embedding
-- distance. The caller passes the query embedding (computed
-- client-side by llm/embeddings.py) plus the raw query text.
--
-- Scoring: each result gets a 0..1 "relevance" where
--   - fuzzy contribution = trigram similarity (0..1)
--   - semantic contribution = 1 - distance (cosine distance 0..2 -> 0..1)
--   - title matches are weighted higher than body matches
-- The two signals are combined with a configurable weight
-- (p_semantic_weight, default 0.5 = equal weighting).

CREATE OR REPLACE FUNCTION hybrid_search(
  p_query           TEXT,
  p_embedding       VECTOR(384),
  p_limit           INT DEFAULT 10,
  p_fuzzy_threshold FLOAT DEFAULT 0.15,
  p_semantic_weight FLOAT DEFAULT 0.5,
  p_exclude_types   TEXT[] DEFAULT NULL,
  p_exclude_tags    TEXT[] DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  WITH fuzzy AS (
    SELECT
      n.id,
      n.title,
      n.type,
      n.body,
      n.confidence,
      GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body),  LOWER(p_query))
      ) AS fuzzy_score,
      -- Title matches are more valuable than body matches
      CASE
        WHEN similarity(LOWER(n.title), LOWER(p_query)) > 0.2 THEN 1.0
        ELSE 0.7
      END AS title_boost
    FROM nodes n
    WHERE
      n.status = 'active'
      AND GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body),  LOWER(p_query))
      ) > p_fuzzy_threshold
      AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
      AND (p_exclude_tags IS NULL OR n.id NOT IN (
        SELECT nt.node_id FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE t.name = ANY(p_exclude_tags)
      ))
  ),
  semantic AS (
    SELECT
      n.id,
      n.title,
      n.type,
      n.body,
      n.confidence,
      -- cosine distance 0..2 -> similarity 0..1
      1.0 - (n.embedding <=> p_embedding) AS semantic_score
    FROM nodes n
    WHERE
      n.status = 'active'
      AND n.embedding IS NOT NULL
      AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
      AND (p_exclude_tags IS NULL OR n.id NOT IN (
        SELECT nt.node_id FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE t.name = ANY(p_exclude_tags)
      ))
  ),
  merged AS (
    SELECT
      COALESCE(f.id, s.id) AS id,
      COALESCE(f.title, s.title) AS title,
      COALESCE(f.type, s.type) AS type,
      COALESCE(f.body, s.body) AS body,
      COALESCE(f.confidence, s.confidence, 0.5) AS confidence,
      -- Combined relevance: weight fuzzy and semantic, apply title boost
      (
        (1.0 - p_semantic_weight) * COALESCE(f.fuzzy_score * f.title_boost, 0)
        + p_semantic_weight * COALESCE(s.semantic_score, 0)
      ) AS relevance
    FROM fuzzy f
    FULL OUTER JOIN semantic s ON f.id = s.id
  )
  SELECT json_agg(json_build_object(
    'id', m.id,
    'title', m.title,
    'type', m.type,
    'body', m.body,
    'confidence', m.confidence,
    'relevance', m.relevance
  ) ORDER BY m.relevance DESC)
  INTO result
  FROM merged m
  WHERE m.relevance > 0
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- Hybrid memory search — same merge logic for the memories table.
-- Used by load_memory_context and memory dedup so semantically
-- similar memories are caught, not just trigram-similar ones.
-- ============================================================

CREATE OR REPLACE FUNCTION hybrid_search_memories(
  p_query           TEXT,
  p_embedding       VECTOR(384),
  p_limit           INT DEFAULT 5,
  p_fuzzy_threshold FLOAT DEFAULT 0.15,
  p_semantic_weight FLOAT DEFAULT 0.5
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  WITH fuzzy AS (
    SELECT
      m.id,
      m.title,
      m.body,
      m.fact_type,
      m.confidence,
      GREATEST(
        similarity(LOWER(m.title), LOWER(p_query)),
        similarity(LOWER(m.body),  LOWER(p_query))
      ) AS fuzzy_score
    FROM memories m
    WHERE
      m.status = 'active'
      AND GREATEST(
        similarity(LOWER(m.title), LOWER(p_query)),
        similarity(LOWER(m.body),  LOWER(p_query))
      ) > p_fuzzy_threshold
  ),
  semantic AS (
    SELECT
      m.id,
      m.title,
      m.body,
      m.fact_type,
      m.confidence,
      1.0 - (m.embedding <=> p_embedding) AS semantic_score
    FROM memories m
    WHERE
      m.status = 'active'
      AND m.embedding IS NOT NULL
  ),
  merged AS (
    SELECT
      COALESCE(f.id, s.id) AS id,
      COALESCE(f.title, s.title) AS title,
      COALESCE(f.body, s.body) AS body,
      COALESCE(f.fact_type, s.fact_type) AS fact_type,
      COALESCE(f.confidence, s.confidence, 0.5) AS confidence,
      (
        (1.0 - p_semantic_weight) * COALESCE(f.fuzzy_score, 0)
        + p_semantic_weight * COALESCE(s.semantic_score, 0)
      ) AS relevance
    FROM fuzzy f
    FULL OUTER JOIN semantic s ON f.id = s.id
  )
  SELECT json_agg(json_build_object(
    'id', m.id,
    'title', m.title,
    'body', m.body,
    'fact_type', m.fact_type,
    'confidence', m.confidence,
    'relevance', m.relevance
  ) ORDER BY m.relevance DESC)
  INTO result
  FROM merged m
  WHERE m.relevance > 0
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- Semantic memory consolidation
-- ============================================================
-- The existing consolidate_memories() only merges memories whose TITLES are
-- trigram-similar. Memories that say the same thing in different words
-- (e.g. "prefers dark mode" vs "likes dark themes") are never merged. This
-- function merges memories whose EMBEDDINGS are close (cosine distance below
-- a threshold), keeping the higher-confidence one and absorbing the other's
-- tags — the same merge policy as the title-based version.

CREATE OR REPLACE FUNCTION consolidate_memories_semantic(
  p_distance_threshold FLOAT DEFAULT 0.35,
  p_limit INT DEFAULT 500
)
RETURNS JSON AS $$
DECLARE
  archived_count INT := 0;
  survivor_count INT := 0;
  result JSON;
BEGIN
  WITH similar_pairs AS (
    SELECT
      a.id AS keep_id,
      b.id AS remove_id,
      a.confidence AS keep_conf,
      b.confidence AS remove_conf
    FROM memories a
    JOIN memories b ON a.id < b.id
    WHERE a.status = 'active'
      AND b.status = 'active'
      AND a.embedding IS NOT NULL
      AND b.embedding IS NOT NULL
      AND (a.embedding <=> b.embedding) < p_distance_threshold
      -- Avoid re-merging pairs already caught by title similarity
      AND similarity(LOWER(a.title), LOWER(b.title)) <= 0.7
    ORDER BY (a.embedding <=> b.embedding)
    LIMIT p_limit
  ),
  decisions AS (
    SELECT
      CASE WHEN keep_conf >= remove_conf THEN keep_id ELSE remove_id END AS survivor_id,
      CASE WHEN keep_conf >= remove_conf THEN remove_id ELSE keep_id END AS archived_id
    FROM similar_pairs
  ),
  archived AS (
    UPDATE memories
    SET status = 'archived',
        confidence = GREATEST(
          memories.confidence,
          COALESCE((SELECT m.confidence FROM memories m WHERE m.id = decisions.survivor_id), 0)
        )
    FROM decisions
    WHERE memories.id = decisions.archived_id
    RETURNING 1
  ),
  survivors AS (
    UPDATE memories
    SET tags = ARRAY(
      SELECT DISTINCT unnest(
        COALESCE(memories.tags, '{}') ||
        COALESCE((SELECT m.tags FROM memories m WHERE m.id = decisions.archived_id), '{}')
      )
    )
    FROM decisions
    WHERE memories.id = decisions.survivor_id
    RETURNING 1
  )
  SELECT
    (SELECT COUNT(*) FROM archived) AS archived_count,
    (SELECT COUNT(*) FROM survivors) AS survivor_count
  INTO archived_count, survivor_count;

  result := json_build_object(
    'merged_count', archived_count,
    'survivor_count', survivor_count
  );

  RETURN result;
END;
$$ LANGUAGE plpgsql;

NOTIFY pgrst, 'reload schema';
