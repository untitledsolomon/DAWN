-- Migration 003: Add auto_threshold column to tags table
-- This stores the learned per-tag threshold for the HybridTagger.
-- Tags with no history default to 0.25 in the application code.

ALTER TABLE tags ADD COLUMN IF NOT EXISTS auto_threshold FLOAT DEFAULT NULL;

-- Also add the exclude filters to fuzzy_search and semantic_search
-- if they don't already exist (needed for the updated RPC signatures)

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
