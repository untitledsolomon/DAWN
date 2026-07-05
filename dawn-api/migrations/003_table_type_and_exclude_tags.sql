-- ============================================================
-- MIGRATION 003: Add 'table' node type + exclude_tags support
-- ============================================================
-- Run this after the base schema. Adds:
--   1. 'table' value to node_type enum
--   2. exclude_tags parameter to fuzzy_search
--   3. exclude_tags parameter to semantic_search
-- ============================================================

-- Step 1: Add 'table' to the node_type enum
-- ALTER TYPE ... ADD VALUE cannot be done in a transaction block
-- in Postgres < 13, so we handle it safely:
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_enum
    WHERE enumlabel = 'table'
      AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'node_type')
  ) THEN
    ALTER TYPE node_type ADD VALUE 'table';
  END IF;
END $$;

-- Step 2: Update fuzzy_search to support exclude_tags
-- exclude_tags filters out nodes that have ANY of the given tag names
CREATE OR REPLACE FUNCTION fuzzy_search(
  p_query       TEXT,
  p_limit       INT DEFAULT 5,
  p_threshold   FLOAT DEFAULT 0.2,
  p_exclude_tags TEXT[] DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  IF p_exclude_tags IS NOT NULL AND array_length(p_exclude_tags, 1) > 0 THEN
    -- With tag exclusion
    SELECT json_agg(subq.* ORDER BY subq.similarity DESC) INTO result
    FROM (
      SELECT
        n.id,
        n.title,
        n.type,
        n.body,
        GREATEST(
          similarity(LOWER(n.title), LOWER(p_query)),
          similarity(LOWER(n.body),  LOWER(p_query))
        ) AS similarity
      FROM nodes n
      WHERE
        n.status = 'active'
        AND GREATEST(
          similarity(LOWER(n.title), LOWER(p_query)),
          similarity(LOWER(n.body),  LOWER(p_query))
        ) > p_threshold
        AND NOT EXISTS (
          SELECT 1
          FROM node_tags nt
          JOIN tags t ON t.id = nt.tag_id
          WHERE nt.node_id = n.id
            AND t.name = ANY(p_exclude_tags)
        )
      ORDER BY similarity DESC
      LIMIT p_limit
    ) subq;
  ELSE
    -- Without tag exclusion (original behavior)
    SELECT json_agg(json_build_object(
      'id', n.id,
      'title', n.title,
      'type', n.type,
      'body', n.body,
      'similarity', GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body),  LOWER(p_query))
      )
    ) ORDER BY GREATEST(
      similarity(LOWER(n.title), LOWER(p_query)),
      similarity(LOWER(n.body),  LOWER(p_query))
    ) DESC) INTO result
    FROM nodes n
    WHERE
      n.status = 'active'
      AND GREATEST(
        similarity(LOWER(n.title), LOWER(p_query)),
        similarity(LOWER(n.body),  LOWER(p_query))
      ) > p_threshold
    LIMIT p_limit;
  END IF;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- Step 3: Update semantic_search to support exclude_tags
CREATE OR REPLACE FUNCTION semantic_search(
  p_embedding   VECTOR(384),
  p_limit       INT DEFAULT 5,
  p_exclude_tags TEXT[] DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  IF p_exclude_tags IS NOT NULL AND array_length(p_exclude_tags, 1) > 0 THEN
    -- With tag exclusion
    SELECT json_agg(json_build_object(
      'id', n.id,
      'title', n.title,
      'type', n.type,
      'body', n.body,
      'distance', n.embedding <=> p_embedding
    ) ORDER BY n.embedding <=> p_embedding) INTO result
    FROM nodes n
    WHERE n.status = 'active'
      AND n.embedding IS NOT NULL
      AND NOT EXISTS (
        SELECT 1
        FROM node_tags nt
        JOIN tags t ON t.id = nt.tag_id
        WHERE nt.node_id = n.id
          AND t.name = ANY(p_exclude_tags)
      )
    LIMIT p_limit;
  ELSE
    -- Without tag exclusion (original behavior)
    SELECT json_agg(json_build_object(
      'id', n.id,
      'title', n.title,
      'type', n.type,
      'body', n.body,
      'distance', n.embedding <=> p_embedding
    ) ORDER BY n.embedding <=> p_embedding) INTO result
    FROM nodes n
    WHERE n.status = 'active'
      AND n.embedding IS NOT NULL
    LIMIT p_limit;
  END IF;

  RETURN result;
END;
$$ LANGUAGE plpgsql;
