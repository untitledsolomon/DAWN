-- Migration 027: learning mode (topics, cards with FSRS state, reviews, quiz attempts, lessons)

CREATE TABLE IF NOT EXISTS learn_topics (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id        UUID REFERENCES learn_topics(id) ON DELETE SET NULL,
    title            TEXT NOT NULL,
    summary          TEXT,
    goal             TEXT,
    level            TEXT NOT NULL DEFAULT 'beginner'
                     CHECK (level IN ('beginner','intermediate','advanced')),
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','paused','archived')),
    prerequisite_ids UUID[] NOT NULL DEFAULT '{}',
    last_studied_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learn_topics_parent ON learn_topics(parent_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_learn_topics_title_parent
    ON learn_topics (lower(title), COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE TABLE IF NOT EXISTS learn_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id         UUID NOT NULL REFERENCES learn_topics(id) ON DELETE CASCADE,
    front            TEXT NOT NULL,
    back             TEXT NOT NULL,
    tags             TEXT[] NOT NULL DEFAULT '{}',
    source_ref       JSONB,                      -- {artifact_id, block_id} or {url}
    status           TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active','suspended','flagged')),
    fsrs             JSONB NOT NULL,
    due              TIMESTAMPTZ NOT NULL DEFAULT now(),
    stability        REAL,
    reps             INTEGER NOT NULL DEFAULT 0,
    again_count      INTEGER NOT NULL DEFAULT 0,
    last_reviewed_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learn_items_due   ON learn_items(due) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_learn_items_topic ON learn_items(topic_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_learn_items_topic_front
    ON learn_items (topic_id, lower(front));

CREATE TABLE IF NOT EXISTS learn_reviews (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_review_id UUID UNIQUE,                 -- idempotency key from the client
    item_id          UUID NOT NULL REFERENCES learn_items(id) ON DELETE CASCADE,
    rating           SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 4),
    reviewed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    duration_ms      INTEGER,
    log              JSONB
);
CREATE INDEX IF NOT EXISTS idx_learn_reviews_item ON learn_reviews(item_id, reviewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_learn_reviews_day  ON learn_reviews(reviewed_at);

CREATE TABLE IF NOT EXISTS learn_attempts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id     UUID REFERENCES learn_topics(id) ON DELETE SET NULL,
    artifact_id  UUID REFERENCES artifacts(id) ON DELETE SET NULL,
    block_id     TEXT,
    question_id  TEXT,
    kind         TEXT NOT NULL CHECK (kind IN ('mcq','short')),
    correct      BOOLEAN,
    self_rating  TEXT CHECK (self_rating IN ('missed','partly','got_it')),
    hints_used   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_learn_attempts_topic ON learn_attempts(topic_id, created_at DESC);

CREATE TABLE IF NOT EXISTS learn_lessons (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id     UUID NOT NULL REFERENCES learn_topics(id) ON DELETE CASCADE,
    artifact_id  UUID NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (artifact_id)
);
CREATE INDEX IF NOT EXISTS idx_learn_lessons_topic ON learn_lessons(topic_id, created_at DESC);

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS learn_topic_id UUID
    REFERENCES learn_topics(id) ON DELETE SET NULL;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS learn_style TEXT
    CHECK (learn_style IN ('explain','coach'));

ALTER TABLE learn_topics   ENABLE ROW LEVEL SECURITY;
ALTER TABLE learn_items    ENABLE ROW LEVEL SECURITY;
ALTER TABLE learn_reviews  ENABLE ROW LEVEL SECURITY;
ALTER TABLE learn_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE learn_lessons  ENABLE ROW LEVEL SECURITY;
NOTIFY pgrst, 'reload schema';
