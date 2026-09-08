-- ──────────────────────────────────────────────────────────────────────────────
-- v42.1: Widen the mcp_servers.server_type check constraint to allow 'http'.
--
-- The `mcp_servers` table (created by 014_mcp_tables.sql) defines server_type
-- as TEXT without a constraint, but a separate CHECK constraint was added
-- outside that migration (allowing only 'stdio' | 'sse' | 'websocket'). That
-- rejected the 'http' server type the frontend and MCP code use, causing
-- POST /mcp/servers to fail with a 500 on HTTP MCP servers.
--
-- This migration is idempotent and safe to run against any deployment.
-- ──────────────────────────────────────────────────────────────────────────────

ALTER TABLE mcp_servers DROP CONSTRAINT IF EXISTS mcp_servers_server_type_check;
ALTER TABLE mcp_servers ADD CONSTRAINT mcp_servers_server_type_check
    CHECK (server_type = ANY (ARRAY['stdio'::text, 'http'::text, 'sse'::text, 'websocket'::text]));

NOTIFY pgrst, 'reload schema';
