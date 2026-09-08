-- ──────────────────────────────────────────────────────────────────────────────
-- v43.1: Add RFC 8707 resource indicator to mcp_oauth_tokens.
--
-- The MCP Authorization spec requires the `resource` parameter in both
-- authorization and token requests. Persist the canonical resource URI per
-- server so token refresh requests can include it too.
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE mcp_oauth_tokens
    ADD COLUMN IF NOT EXISTS resource TEXT;

NOTIFY pgrst, 'reload schema';
