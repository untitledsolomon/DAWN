-- ============================================================
-- DAWN KNOWLEDGE GRAPH SCHEMA
-- Supabase / Postgres
-- Run extensions first, then tables in order
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- fuzzy text matching


-- ============================================================
-- ENUMS
-- Keep these narrow — add values deliberately, not speculatively
-- ============================================================

CREATE TYPE node_type AS ENUM (
  'concept',        -- abstract idea, definition, principle
  'entity',         -- a real thing: product, person, company, tool
  'process',        -- a workflow, procedure, sequence of steps
  'fact',           -- a specific piece of information, a state
  'memory',         -- derived from conversation, personal context
  'document'        -- ingested from a file or repo
);

CREATE TYPE edge_relation AS ENUM (
  'is_a',           -- Sentinel is_a trading_bot
  'part_of',        -- Compressor part_of Jet_Engine
  'depends_on',     -- Forge depends_on Supabase
  'produces',       -- nyao_scalper produces XAUUSD_trades
  'causes',         -- martingale_bug causes dig_and_recover_loss
  'requires',       -- Axis requires Uganda_payroll_compliance
  'see_also',       -- loose association, non-typed link
  'precedes',       -- Step_1 precedes Step_2 (process ordering)
  'owned_by',       -- Regent_CRM owned_by Regent
  'related_to',     -- fallback general relation
  'contradicts',    -- conflicting facts, useful for memory hygiene
  'derived_from'    -- memory node derived_from a conversation
);

CREATE TYPE ingestion_source AS ENUM (
  'manual',         -- you wrote it directly
  'repo',           -- pulled from a git repo
  'conversation',   -- extracted from a Jarvis/DAWN session
  'document',       -- parsed from a PDF, doc, or file
  'web'             -- fetched from the internet
);

CREATE TYPE node_status AS ENUM (
  'active',         -- in use, trusted
  'stale',          -- may be outdated, needs review
  'archived',       -- no longer relevant, kept for history
  'draft'           -- pending review before becoming active
);


-- ============================================================
-- CORE TABLES
-- ============================================================

-- NODES — atomic units of knowledge
CREATE TABLE nodes (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  title           TEXT NOT NULL,                        -- short name, used for entity resolution
  type            node_type NOT NULL,
  body            TEXT,                                 -- the actual content, kept short
  status          node_status NOT NULL DEFAULT 'active',
  source          ingestion_source NOT NULL DEFAULT 'manual',
  source_ref      TEXT,                                 -- e.g. repo path, file name, conversation_id
  embedding       VECTOR(384),                          -- for semantic fallback search (all-MiniLM-L6-v2 dimensions)
  confidence      FLOAT DEFAULT 1.0,                   -- 0-1, lower for auto-extracted uncertain facts
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW(),
  reviewed_at     TIMESTAMPTZ,                          -- last time a human confirmed this is still accurate
  CONSTRAINT title_not_empty CHECK (char_length(title) > 0)
);

-- TAGS — vocabulary-controlled labels
CREATE TABLE tags (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name            TEXT NOT NULL UNIQUE,                 -- e.g. "trading", "regent", "personal", "econ-sim"
  description     TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- NODE_TAGS — many-to-many
CREATE TABLE node_tags (
  node_id         UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  tag_id          UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (node_id, tag_id)
);

-- EDGES — typed relationships between nodes
CREATE TABLE edges (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  from_node       UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  to_node         UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  relation        edge_relation NOT NULL,
  weight          FLOAT DEFAULT 1.0,                   -- for ranking traversal paths
  note            TEXT,                                 -- optional human annotation on why this link exists
  source          ingestion_source NOT NULL DEFAULT 'manual',
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT no_self_loop CHECK (from_node != to_node)
);

-- MEMORY NODES — conversations that produced durable facts
-- Memory facts are regular nodes (type = 'memory') but we track
-- their session origin here for hygiene/review
CREATE TABLE memory_sessions (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  session_source  TEXT NOT NULL,                        -- 'jarvis', 'dawn_web', 'dawn_android'
  summary         TEXT,                                 -- brief description of what the session was about
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Links a memory node back to the session it came from
CREATE TABLE memory_node_origins (
  node_id         UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
  session_id      UUID NOT NULL REFERENCES memory_sessions(id) ON DELETE CASCADE,
  PRIMARY KEY (node_id, session_id)
);

-- INGESTION LOG — audit trail for auto-ingested content
CREATE TABLE ingestion_log (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source          ingestion_source NOT NULL,
  source_ref      TEXT NOT NULL,                        -- repo path, file name, URL, conversation_id
  nodes_created   INT DEFAULT 0,
  edges_created   INT DEFAULT 0,
  status          TEXT DEFAULT 'success',               -- success | partial | failed
  error           TEXT,
  ingested_at     TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================
-- INDEXES
-- ============================================================

-- Fast exact title lookup (entity resolution step 1)
-- Per-source_ref unique index so two files with the same name
-- in different repos don't collide (e.g. two README.md files)
CREATE UNIQUE INDEX idx_nodes_title_source ON nodes (LOWER(title), COALESCE(source_ref, ''));

-- Trigram index for fuzzy title matching (entity resolution step 2)
CREATE INDEX idx_nodes_title_trgm ON nodes USING GIN (title gin_trgm_ops);

-- Trigram on body too for full-text fallback
CREATE INDEX idx_nodes_body_trgm ON nodes USING GIN (body gin_trgm_ops);

-- Vector index for semantic search (entity resolution step 3 / fallback)
CREATE INDEX idx_nodes_embedding ON nodes USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Fast edge traversal from a node
CREATE INDEX idx_edges_from_node ON edges (from_node);
CREATE INDEX idx_edges_to_node ON edges (to_node);

-- Filter edges by relation type during traversal
CREATE INDEX idx_edges_relation ON edges (relation);

-- Tag lookups
CREATE INDEX idx_node_tags_node ON node_tags (node_id);
CREATE INDEX idx_node_tags_tag ON node_tags (tag_id);

-- Status filter (active nodes only in most queries)
CREATE INDEX idx_nodes_status ON nodes (status);

-- Type filter
CREATE INDEX idx_nodes_type ON nodes (type);


-- ============================================================
-- FUNCTIONS
-- ============================================================

-- Auto-update updated_at on node changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER nodes_updated_at
  BEFORE UPDATE ON nodes
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- TOOL 1: get_node
-- Returns a node + its direct edges (one hop)
-- Used when you already know the exact node you want
CREATE OR REPLACE FUNCTION get_node(p_id UUID)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'node', row_to_json(n),
    'tags', (
      SELECT json_agg(t.name)
      FROM node_tags nt
      JOIN tags t ON t.id = nt.tag_id
      WHERE nt.node_id = n.id
    ),
    'edges_out', (
      SELECT json_agg(json_build_object(
        'relation', e.relation,
        'to_node_id', e.to_node,
        'to_node_title', n2.title,
        'weight', e.weight
      ))
      FROM edges e
      JOIN nodes n2 ON n2.id = e.to_node
      WHERE e.from_node = n.id AND n2.status = 'active'
    ),
    'edges_in', (
      SELECT json_agg(json_build_object(
        'relation', e.relation,
        'from_node_id', e.from_node,
        'from_node_title', n3.title,
        'weight', e.weight
      ))
      FROM edges e
      JOIN nodes n3 ON n3.id = e.from_node
      WHERE e.to_node = n.id AND n3.status = 'active'
    )
  ) INTO result
  FROM nodes n
  WHERE n.id = p_id AND n.status = 'active';

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- TOOL 2: traverse
-- BFS traversal from a starting node, up to max_depth hops
-- Optionally filter by relation types
CREATE OR REPLACE FUNCTION traverse(
  p_start_id      UUID,
  p_relations     edge_relation[] DEFAULT NULL,   -- NULL = follow all relation types
  p_max_depth     INT DEFAULT 2
)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  WITH RECURSIVE graph_walk AS (
    -- Base case: starting node
    SELECT
      n.id,
      n.title,
      n.type,
      n.body,
      n.confidence,
      NULL::UUID AS via_edge,
      NULL::edge_relation AS via_relation,
      NULL::UUID AS parent_id,
      0 AS depth
    FROM nodes n
    WHERE n.id = p_start_id AND n.status = 'active'

    UNION ALL

    -- Recursive case: follow edges outward
    SELECT
      n.id,
      n.title,
      n.type,
      n.body,
      n.confidence,
      e.id AS via_edge,
      e.relation AS via_relation,
      gw.id AS parent_id,
      gw.depth + 1
    FROM graph_walk gw
    JOIN edges e ON e.from_node = gw.id
    JOIN nodes n ON n.id = e.to_node
    WHERE
      gw.depth < p_max_depth
      AND n.status = 'active'
      AND (p_relations IS NULL OR e.relation = ANY(p_relations))
  )
  SELECT json_agg(
    json_build_object(
      'id', id,
      'title', title,
      'type', type,
      'body', body,
      'confidence', confidence,
      'depth', depth,
      'via_relation', via_relation,
      'parent_id', parent_id
    )
    ORDER BY depth, title
  ) INTO result
  FROM (SELECT DISTINCT ON (id) * FROM graph_walk ORDER BY id, depth) deduped;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- TOOL 3: search_tags
-- Find all active nodes with a given tag
CREATE OR REPLACE FUNCTION search_tags(p_tag_name TEXT)
RETURNS JSON AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_agg(json_build_object(
    'id', n.id,
    'title', n.title,
    'type', n.type,
    'body', n.body
  )) INTO result
  FROM nodes n
  JOIN node_tags nt ON nt.node_id = n.id
  JOIN tags t ON t.id = nt.tag_id
  WHERE LOWER(t.name) = LOWER(p_tag_name)
    AND n.status = 'active';

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- TOOL 4: fuzzy_search
-- Trigram similarity search on title + body
-- Falls back to this when exact match fails
CREATE OR REPLACE FUNCTION fuzzy_search(
  p_query     TEXT,
  p_limit     INT DEFAULT 5,
  p_threshold FLOAT DEFAULT 0.2
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
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- BONUS TOOL 5: semantic_search
-- Vector similarity search — only called when fuzzy_search also misses
-- Requires embeddings to be pre-computed and stored on nodes
CREATE OR REPLACE FUNCTION semantic_search(
  p_embedding VECTOR(384),
  p_limit     INT DEFAULT 5
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
  LIMIT p_limit;

  RETURN result;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- SEED DATA — core taxonomy tags
-- These are the top-level tags that structure DAWN's world
-- Add more as the graph grows, don't over-engineer upfront
-- ============================================================

INSERT INTO tags (name, description) VALUES
  ('regent',          'Regent platform and products'),
  ('trading',         'Algorithmic trading systems and strategies'),
  ('econ-sim',        'EconSim C++ town economy simulator'),
  ('mabruk',          'Mabruk Atelier luxury fashion brand'),
  ('personal',        'Solomon personal preferences, habits, context'),
  ('infrastructure',  'VPS, Docker, Coolify, deployment'),
  ('ai',              'AI models, agents, inference, training'),
  ('finance',         'Financial concepts, markets, instruments'),
  ('software',        'General software engineering concepts'),
  ('uganda',          'Uganda-specific context, regulations, market'),
  ('client',          'Regent clients and engagements'),
  ('jarvis',          'Jarvis agent, OpenClaw, Paperclip stack'),
  ('dawn',            'DAWN system itself, its own knowledge');
