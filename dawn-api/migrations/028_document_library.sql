-- Migration 028: document library (full-text, hybrid retrieval). New tables use
-- the library_ prefix because `documents` already exists (document editing).

CREATE OR REPLACE FUNCTION default_client_id() RETURNS UUID
LANGUAGE sql STABLE SET search_path = public AS $$ SELECT id FROM clients WHERE slug = 'regent' $$;

CREATE TABLE IF NOT EXISTS library_collections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       UUID NOT NULL DEFAULT default_client_id() REFERENCES clients(id),
    name            TEXT NOT NULL,
    description     TEXT,
    root_url        TEXT,
    allowed_hosts   TEXT[] NOT NULL DEFAULT '{}',
    classification  TEXT NOT NULL DEFAULT 'public_docs'
                    CHECK (classification IN ('public_docs','internal','client_confidential')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (client_id, name)
);

CREATE TABLE IF NOT EXISTS library_documents (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id      UUID NOT NULL DEFAULT default_client_id() REFERENCES clients(id),
    title          TEXT NOT NULL,
    kind           TEXT NOT NULL CHECK (kind IN ('book','docs_page','paper','article','api_reference','report','other')),
    source_type    TEXT NOT NULL CHECK (source_type IN ('upload','url','crawl','github','legacy_nodes')),
    source_url     TEXT,
    source_name    TEXT,
    collection_id  UUID REFERENCES library_collections(id),
    book_id        UUID REFERENCES books(id) ON DELETE SET NULL,
    classification TEXT NOT NULL DEFAULT 'internal'
                   CHECK (classification IN ('public_docs','internal','client_confidential')),
    content_hash   TEXT NOT NULL,
    text_hash      TEXT,
    storage_ref    TEXT,
    mime           TEXT,
    bytes          BIGINT,
    page_count     INT,
    language       TEXT,
    license        TEXT,
    version_label  TEXT,
    etag           TEXT,
    last_modified  TEXT,
    fetched_at     TIMESTAMPTZ,
    refresh_policy TEXT NOT NULL DEFAULT 'manual' CHECK (refresh_policy IN ('manual','weekly','monthly')),
    status         TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','ready','partial','failed','archived')),
    current_generation INT NOT NULL DEFAULT 0,
    error          TEXT,
    chunk_count    INT NOT NULL DEFAULT 0,
    embedded_count INT NOT NULL DEFAULT 0,
    summary        TEXT,
    graph_node_id  UUID,
    tags           TEXT[] NOT NULL DEFAULT '{}',
    metadata       JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_library_documents_source ON library_documents (client_id, source_url)
    WHERE source_url IS NOT NULL AND status <> 'archived';
CREATE INDEX IF NOT EXISTS idx_library_documents_hash ON library_documents (client_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_library_documents_collection ON library_documents (collection_id);

CREATE TABLE IF NOT EXISTS library_chunks (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id     UUID NOT NULL,
    document_id   UUID NOT NULL REFERENCES library_documents(id) ON DELETE CASCADE,
    generation    INT NOT NULL,
    ordinal       INT NOT NULL,
    section_path  TEXT,
    page_start    INT,
    page_end      INT,
    text          TEXT NOT NULL,
    token_count   INT,
    kind          TEXT NOT NULL DEFAULT 'prose' CHECK (kind IN ('prose','code','table','list','heading')),
    fts           TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(section_path,'') || ' ' || text)) STORED,
    embedding     VECTOR(384),
    UNIQUE (document_id, generation, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_library_chunks_fts ON library_chunks USING GIN (fts);
CREATE INDEX IF NOT EXISTS idx_library_chunks_doc ON library_chunks (client_id, document_id, generation, ordinal);
-- Build the HNSW vector index AFTER the first bulk load, with raised
-- maintenance_work_mem (see the spec):
-- CREATE INDEX idx_library_chunks_embedding ON library_chunks USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION library_embedding_search(p_client UUID, p_embedding VECTOR, p_limit INT DEFAULT 10)
RETURNS TABLE (chunk_id BIGINT, document_id UUID, title TEXT, section_path TEXT, page_start INT, page_end INT,
               source_url TEXT, score REAL, "text" TEXT)
LANGUAGE sql STABLE SET search_path = public AS $$
  SELECT c.id, d.id, d.title, c.section_path, c.page_start, c.page_end, d.source_url,
         1 - (c.embedding <=> p_embedding) AS score, c.text
  FROM library_chunks c
  JOIN library_documents d ON d.id = c.document_id
  WHERE c.client_id = p_client AND c.generation = d.current_generation
        AND d.status IN ('ready','partial') AND c.embedding IS NOT NULL
  ORDER BY c.embedding <=> p_embedding
  LIMIT p_limit;
$$;

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id     UUID NOT NULL DEFAULT default_client_id() REFERENCES clients(id),
    document_id   UUID REFERENCES library_documents(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('fetch','parse','embed','crawl','refresh','reembed','legacy_migrate')),
    params        JSONB NOT NULL DEFAULT '{}',
    status        TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','done','failed','cancelled','needs_approval')),
    stage         TEXT,
    progress      JSONB NOT NULL DEFAULT '{}',
    attempts      INT NOT NULL DEFAULT 0,
    error_class   TEXT,
    error         TEXT,
    requested_by  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs (status, created_at);

CREATE TABLE IF NOT EXISTS ingest_domain_policy (
    client_id   UUID NOT NULL DEFAULT default_client_id() REFERENCES clients(id),
    host        TEXT NOT NULL,
    decision    TEXT NOT NULL CHECK (decision IN ('allow','deny')),
    decided_by  TEXT,
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (client_id, host)
);

CREATE TABLE IF NOT EXISTS library_access_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    client_id    UUID NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL CHECK (action IN ('search','read','ingest','delete','export')),
    document_ids UUID[] NOT NULL DEFAULT '{}',
    query        TEXT,
    result_count INT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_library_access_log_client ON library_access_log (client_id, created_at DESC);

ALTER TABLE library_collections ENABLE ROW LEVEL SECURITY;
ALTER TABLE library_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE library_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingest_domain_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE library_access_log ENABLE ROW LEVEL SECURITY;
NOTIFY pgrst, 'reload schema';
