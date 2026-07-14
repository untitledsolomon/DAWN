-- ============================================================
-- MIGRATION 009: Unified search + dedicated memory table + auto-promotion
-- ============================================================
-- This migration:
--   1. Creates a dedicated `memories` table separate from `nodes`
--   2. Creates a unified `search_all` RPC that does fuzzy + semantic + memory in one call
--   3. Adds auto-promotion trigger for high-confidence memories
--   4. Adds temporal decay function for memory confidence
--   5. Creates an in-memory query cache table
-- ============================================================

-- ============================================================
-- PART 1: Dedicated memories table
-- ============================================================
-- Separate from `nodes` so memory retrieval doesn't pollute
-- concept/entity/document search and vice versa.

CREATE TABLE IF NOT EXISTS memories (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title           TEXT NOT NULL,
  body            TEXT,
  fact_type       TEXT DEFAULT 'preference',  -- 'preference', 'fact', 'decision', 'pattern'
  confidence      FLOAT DEFAULT 0.7,
  status          TEXT DEFAULT 'draft',       -- 'draft', 'active', 'stale', 'archived'
  source          TEXT DEFAULT 'conversation', -- 'conversation', 'manual', 'inferred'
  source_ref      TEXT,                        -- session_id or conversation_id
  embedding       VECTOR(384),
  tags            TEXT[] DEFAULT '{}',
  last_accessed   TIMESTAMPTZ DEFAULT NOW(),
  access_count    INT DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT title_not_empty CHECK (char_length(title) > 0)
);

-- Trigram index for fuzzy title matching
CREATE INDEX IF NOT EXISTS idx_memories_title_trgm ON memories USING GIN (title gin_trgm_ops);

-- Trigram on body too
CREATE INDEX IF NOT EXISTS idx_memories_body_trgm ON memories USING GIN (body gin_trgm_ops);

-- Vector index for semantic search
CREATE INDEX IF NOT EXISTS idx_memories_embedding ON memories USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 50);

-- Status filter
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories (status);

-- Confidence filter (for auto-promotion queries)
CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories (confidence);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_memories_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS memories_updated_at ON memories;
CREATE TRIGGER memories_updated_at
  BEFORE UPDATE ON memories
  FOR EACH ROW EXECUTE FUNCTION update_memories_updated_at();

-- ============================================================
-- PART 2: Memory session tracking (enhanced)
-- ============================================================

-- Add embedding column to memory_sessions if not exists
ALTER TABLE memory_sessions ADD COLUMN IF NOT EXISTS embedding VECTOR(384);

-- ============================================================
-- PART 3: Auto-promotion trigger for high-confidence memories
-- ============================================================
-- When a memory is inserted or updated with confidence >= 0.8,
-- automatically promote it to 'active' status so it's immediately
-- findable without manual review.

CREATE OR REPLACE FUNCTION auto_promote_memory()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.confidence >= 0.8 AND NEW.status = 'draft' THEN
    NEW.status = 'active';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS auto_promote_memory_trigger ON memories;
CREATE TRIGGER auto_promote_memory_trigger
  BEFORE INSERT OR UPDATE ON memories
  FOR EACH ROW
  EXECUTE FUNCTION auto_promote_memory();

-- ============================================================
-- PART 4: Temporal decay function
-- ============================================================
-- Reduce confidence of memories that haven't been accessed or
-- reinforced. Call this periodically (e.g. daily cron).

CREATE OR REPLACE FUNCTION decay_memory_confidence(
  p_days_threshold INT DEFAULT 30,
  p_decay_factor FLOAT DEFAULT 0.05
)
RETURNS INT AS $$
DECLARE
  affected INT;
BEGIN
  UPDATE memories
  SET confidence = GREATEST(confidence - p_decay_factor, 0.1),
      status = CASE
        WHEN confidence - p_decay_factor <= 0.3 THEN 'stale'
        ELSE status
      END
  WHERE status = 'active'
    AND last_accessed < NOW() - (p_days_threshold || ' days')::INTERVAL
    AND confidence > 0.1;
  
  GET DIAGNOSTICS affected = ROW_COUNT;
  RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PART 5: Unified search_all RPC
-- ============================================================
-- Does fuzzy search + semantic search + memory search in ONE
-- database call instead of 4-8 separate RPCs.
-- Returns results grouped by source type.

CREATE OR REPLACE FUNCTION search_all(
  p_query           TEXT,
  p_limit           INT DEFAULT 5,
  p_threshold       FLOAT DEFAULT 0.2,
  p_exclude_types   TEXT[] DEFAULT NULL,
  p_exclude_tags    TEXT[] DEFAULT NULL,
  p_include_memories BOOLEAN DEFAULT TRUE,
  p_embedding       VECTOR(384) DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
  fuzzy_results JSON;
  semantic_results JSON;
  memory_results JSON;
BEGIN
  -- 1. Fuzzy search on nodes (same as existing fuzzy_search)
  SELECT json_agg(subq.* ORDER BY subq.similarity DESC) INTO fuzzy_results
  FROM (
    SELECT
      n.id,
      n.title,
      n.type,
      n.body,
      n.confidence,
      'node' AS source_type,
      GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body), LOWER(p_query))
      ) AS similarity,
      NULL::float AS distance
    FROM nodes n
    WHERE
      n.status = 'active'
      AND GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body), LOWER(p_query))
      ) > p_threshold
      AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
      AND (p_exclude_tags IS NULL OR n.id NOT IN (
        SELECT nt.node_id FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE t.name = ANY(p_exclude_tags)
      ))
    ORDER BY similarity DESC
    LIMIT p_limit
  ) subq;

  -- 2. Semantic search on nodes (if embedding provided)
  IF p_embedding IS NOT NULL THEN
    SELECT json_agg(json_build_object(
      'id', n.id,
      'title', n.title,
      'type', n.type,
      'body', n.body,
      'confidence', n.confidence,
      'source_type', 'node',
      'similarity', NULL::float,
      'distance', n.embedding <=> p_embedding
    ) ORDER BY n.embedding <=> p_embedding) INTO semantic_results
    FROM nodes n
    WHERE n.status = 'active'
      AND n.embedding IS NOT NULL
      AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
      AND (p_exclude_tags IS NULL OR n.id NOT IN (
        SELECT nt.node_id FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE t.name = ANY(p_exclude_tags)
      ))
    LIMIT p_limit;
  END IF;

  -- 3. Memory search (if enabled)
  IF p_include_memories THEN
    -- Fuzzy match on memories
    SELECT json_agg(subq.* ORDER BY subq.similarity DESC) INTO memory_results
    FROM (
      SELECT
        m.id,
        m.title,
        'memory' AS type,
        m.body,
        m.confidence,
        'memory' AS source_type,
        GREATEST(
          similarity(LOWER(m.title), LOWER(p_query)),
          similarity(LOWER(m.body), LOWER(p_query))
        ) AS similarity,
        NULL::float AS distance,
        m.fact_type,
        m.tags,
        m.last_accessed,
        m.access_count
      FROM memories m
      WHERE
        m.status = 'active'
        AND GREATEST(
          similarity(LOWER(m.title), LOWER(p_query)),
          similarity(LOWER(m.body), LOWER(p_query))
        ) > p_threshold
      ORDER BY similarity DESC
      LIMIT p_limit
    ) subq;

    -- If fuzzy found nothing on memories, try semantic
    IF (memory_results IS NULL OR memory_results = 'null'::json) AND p_embedding IS NOT NULL THEN
      SELECT json_agg(json_build_object(
        'id', m.id,
        'title', m.title,
        'type', 'memory',
        'body', m.body,
        'confidence', m.confidence,
        'source_type', 'memory',
        'similarity', NULL::float,
        'distance', m.embedding <=> p_embedding,
        'fact_type', m.fact_type,
        'tags', m.tags,
        'last_accessed', m.last_accessed,
        'access_count', m.access_count
      ) ORDER BY m.embedding <=> p_embedding) INTO memory_results
      FROM memories m
      WHERE m.status = 'active'
        AND m.embedding IS NOT NULL
      LIMIT p_limit;
    END IF;
  END IF;

  -- Assemble final result
  result := json_build_object(
    'nodes_fuzzy', COALESCE(fuzzy_results, '[]'::json),
    'nodes_semantic', COALESCE(semantic_results, '[]'::json),
    'memories', COALESCE(memory_results, '[]'::json)
  );

  RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PART 6: Query cache table
-- ============================================================
-- Simple server-side cache for frequent queries.
-- DAWN writes to this from Python; the table just stores results.

CREATE TABLE IF NOT EXISTS query_cache (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query_hash      TEXT NOT NULL UNIQUE,       -- MD5 of the normalized query
  query_text      TEXT NOT NULL,
  result          JSONB NOT NULL,
  result_type     TEXT DEFAULT 'search',      -- 'search', 'traverse', 'memory'
  hit_count       INT DEFAULT 1,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '5 minutes')
);

CREATE INDEX IF NOT EXISTS idx_query_cache_hash ON query_cache (query_hash);
CREATE INDEX IF NOT EXISTS idx_query_cache_expires ON query_cache (expires_at);

-- Auto-cleanup expired cache entries
CREATE OR REPLACE FUNCTION cleanup_query_cache()
RETURNS INT AS $$
DECLARE
  deleted INT;
BEGIN
  DELETE FROM query_cache WHERE expires_at < NOW();
  GET DIAGNOSTICS deleted = ROW_COUNT;
  RETURN deleted;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PART 7: Memory consolidation function
-- ============================================================
-- Find and merge duplicate or contradictory memories.
-- Called periodically or on-demand.

CREATE OR REPLACE FUNCTION consolidate_memories()
RETURNS JSON AS $$
DECLARE
  duplicates INT := 0;
  merged INT := 0;
  result JSON;
BEGIN
  -- Find memories with very similar titles (trigram similarity > 0.7)
  -- and merge them: keep the one with highest confidence, archive the rest
  WITH similar_pairs AS (
    SELECT
      a.id AS keep_id,
      b.id AS remove_id,
      a.title AS keep_title,
      b.title AS remove_title,
      a.confidence AS keep_conf,
      b.confidence AS remove_conf,
      similarity(LOWER(a.title), LOWER(b.title)) AS sim
    FROM memories a
    JOIN memories b ON a.id < b.id
    WHERE a.status = 'active'
      AND b.status = 'active'
      AND similarity(LOWER(a.title), LOWER(b.title)) > 0.7
  ),
  -- For each pair, decide which to keep (higher confidence wins)
  decisions AS (
    SELECT
      CASE WHEN keep_conf >= remove_conf THEN keep_id ELSE remove_id END AS survivor_id,
      CASE WHEN keep_conf >= remove_conf THEN remove_id ELSE keep_id END AS archived_id
    FROM similar_pairs
  ),
  -- Archive the losers
  archived AS (
    UPDATE memories
    SET status = 'archived',
        body = COALESCE(
          (SELECT m.body FROM memories m WHERE m.id = decisions.survivor_id),
          memories.body
        ),
        confidence = GREATEST(
          memories.confidence,
          COALESCE((SELECT m.confidence FROM memories m WHERE m.id = decisions.survivor_id), 0)
        )
    FROM decisions
    WHERE memories.id = decisions.archived_id
    RETURNING 1
  ),
  -- Update survivor to absorb the archived one's tags
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
  INTO duplicates, merged;

  result := json_build_object(
    'duplicates_found', duplicates,
    'merged_count', merged
  );

  RETURN result;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PART 8: Update memory access tracking function
-- ============================================================
-- Call this whenever a memory is retrieved to update its
-- last_accessed timestamp and access_count for decay calculations.

CREATE OR REPLACE FUNCTION touch_memory(p_memory_id UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE memories
  SET last_accessed = NOW(),
      access_count = access_count + 1
  WHERE id = p_memory_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- PART 9: Batch touch memories (for when multiple are retrieved)
-- ============================================================

CREATE OR REPLACE FUNCTION touch_memories_batch(p_memory_ids UUID[])
RETURNS VOID AS $$
BEGIN
  UPDATE memories
  SET last_accessed = NOW(),
      access_count = access_count + 1
  WHERE id = ANY(p_memory_ids);
END;
$$ LANGUAGE plpgsql;

-- Force PostgREST to reload its schema cache
NOTIFY pgrst, 'reload schema';
