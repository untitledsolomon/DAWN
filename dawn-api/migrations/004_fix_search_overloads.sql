-- ============================================================
-- MIGRATION 004: Fix PGRST203 ambiguous overload errors
-- ============================================================
-- Root cause: earlier migrations used CREATE OR REPLACE FUNCTION
-- with DIFFERENT parameter lists for semantic_search / fuzzy_search.
-- Postgres treats a different signature as a NEW overload rather
-- than a replacement, so multiple versions of each function now
-- coexist. PostgREST can't pick one when called with a subset of
-- args that matches more than one overload -> PGRST203.
--
-- Fix: explicitly drop every old overload, leaving only the
-- canonical (p_query/p_embedding, p_limit, p_exclude_types,
-- p_exclude_tags) signature in place.
-- ============================================================

-- semantic_search overloads to remove
DROP FUNCTION IF EXISTS semantic_search(public.vector, integer);
DROP FUNCTION IF EXISTS semantic_search(public.vector, integer, text[]);

-- fuzzy_search overloads to remove
DROP FUNCTION IF EXISTS fuzzy_search(text, integer, float);
DROP FUNCTION IF EXISTS fuzzy_search(text, integer, float, text[]);

-- This overload isn't in any committed migration -- it appears to have
-- been created directly against the DB (e.g. via SQL editor) using the
-- node_type enum array instead of text[] for p_exclude_types. It's the
-- one actually colliding with the canonical version below, so drop both
-- possible forms defensively.
DROP FUNCTION IF EXISTS fuzzy_search(text, integer, float, node_type[], text[]);
DROP FUNCTION IF EXISTS fuzzy_search(text, integer, float, text[], text[]);

-- Same defensive drop for semantic_search in case a node_type[] variant
-- was created there too.
DROP FUNCTION IF EXISTS semantic_search(public.vector, integer, node_type[], text[]);
DROP FUNCTION IF EXISTS semantic_search(public.vector, integer, text[], text[]);

-- Recreate the canonical versions (safe no-op if identical to migration 003_add_auto_threshold)
CREATE OR REPLACE FUNCTION fuzzy_search(
  p_query         TEXT,
  p_limit         INT DEFAULT 5,
  p_threshold     FLOAT DEFAULT 0.2,
  p_exclude_types TEXT[] DEFAULT NULL,
  p_exclude_tags  TEXT[] DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
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
    AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
    AND (p_exclude_tags IS NULL OR n.id NOT IN (
      SELECT nt.node_id FROM node_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE t.name = ANY(p_exclude_tags)
    ))
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION semantic_search(
  p_embedding     VECTOR(384),
  p_limit         INT DEFAULT 5,
  p_exclude_types TEXT[] DEFAULT NULL,
  p_exclude_tags  TEXT[] DEFAULT NULL
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
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
    AND (p_exclude_types IS NULL OR n.type::text != ALL(p_exclude_types))
    AND (p_exclude_tags IS NULL OR n.id NOT IN (
      SELECT nt.node_id FROM node_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE t.name = ANY(p_exclude_tags)
    ))
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;

-- Force PostgREST to reload its schema cache so the dropped
-- overloads disappear immediately instead of after the next restart.
NOTIFY pgrst, 'reload schema';
