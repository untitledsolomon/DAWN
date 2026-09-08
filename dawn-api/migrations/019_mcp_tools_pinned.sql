-- ─────────────────────────────────────────────────────────────────────────────
-- v43.0: Progressive discovery — add `pinned` to mcp_tools.
--
-- Under progressive discovery (Anthropic client best-practice model), DAWN no
-- longer eagerly registers every discovered MCP tool as a first-class
-- `mcp_<name>` DAWN tool. Instead the catalog is reachable via the lightweight
-- `mcp_search_tools` meta-tool and execution via `mcp_call_tool`. A user can
-- still promote their most-used remote tools to always-available first-class
-- tools by marking them `pinned`.
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE mcp_tools ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;

-- Index for the startup query that loads only pinned tools.
CREATE INDEX IF NOT EXISTS idx_mcp_tools_pinned ON mcp_tools (pinned) WHERE pinned = TRUE;

NOTIFY pgrst, 'reload schema';
