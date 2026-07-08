-- Migration 007: Explainer artifacts
-- Extends the artifacts table to support animated explainer HTML fragments
-- alongside existing Vega-Lite charts, tables, images, and files.

-- 1. Widen the type CHECK constraint to include 'explainer'
ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_type_check;
ALTER TABLE artifacts ADD CONSTRAINT artifacts_type_check
  CHECK (type IN ('chart', 'table', 'image', 'file', 'explainer'));

-- 2. Add columns for explainer artifacts
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS code TEXT;
  -- Self-contained HTML/SVG/JS bundle (the explainer fragment)

ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS prompt TEXT;
  -- Original user question, for regeneration/debugging

ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';
  -- { diagram_type, duration_estimate, model_used, ... }

-- 3. Add user_id and conversation_id columns (nullable for backward compat)
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS conversation_id UUID;

-- 4. Index for listing explainers by type
CREATE INDEX IF NOT EXISTS idx_artifacts_explainer_type ON artifacts(type) WHERE type = 'explainer';

-- 5. Index for user-scoped queries
CREATE INDEX IF NOT EXISTS idx_artifacts_user_id ON artifacts(user_id);

-- 6. Index for conversation-scoped queries
CREATE INDEX IF NOT EXISTS idx_artifacts_conversation_id ON artifacts(conversation_id);
