-- ============================================================
-- MIGRATION 005: Add `mode` to chat_sessions
-- ============================================================
-- The chat, agent, and visualize pages all share the same
-- chat_sessions/chat_messages tables, but sessions had no way to
-- record which page created them. That meant the sidebar could only
-- ever link to /chat?id=..., so opening a session created from the
-- Visualize page dropped you into plain chat instead — the messages
-- were still there (same table), just the wrong page/tool context.
-- ============================================================

ALTER TABLE chat_sessions
  ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'chat';

-- Keep it to the three modes the frontend actually has pages for.
ALTER TABLE chat_sessions
  DROP CONSTRAINT IF EXISTS chat_sessions_mode_check;
ALTER TABLE chat_sessions
  ADD CONSTRAINT chat_sessions_mode_check CHECK (mode IN ('chat', 'agent', 'visualize'));

CREATE INDEX IF NOT EXISTS idx_chat_sessions_mode ON chat_sessions(mode);

NOTIFY pgrst, 'reload schema';
