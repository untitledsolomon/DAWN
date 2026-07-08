-- Migration 006: Link artifacts to chat messages
-- Adds artifact_ids column to chat_messages so we know which artifacts
-- belong to which message within a session.

ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS artifact_ids UUID[] DEFAULT '{}';

-- Index for finding messages that have artifacts
CREATE INDEX IF NOT EXISTS idx_chat_messages_artifact_ids ON chat_messages USING GIN (artifact_ids);
