-- ──────────────────────────────────────────────────────────────────────────────
-- v41.0: MCP tables — external MCP server registry, discovered tools, and
-- tool permissions. These tables are referenced by routers/mcp.py and
-- tools/mcp_server.py but were never created; this migration adds them.
-- ──────────────────────────────────────────────────────────────────────────────

-- Registered external MCP servers (stdio or HTTP/streamable).
CREATE TABLE IF NOT EXISTS mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    server_type TEXT NOT NULL DEFAULT 'stdio',   -- 'stdio' | 'http'
    command TEXT,                                 -- for stdio: executable
    args TEXT[] DEFAULT '{}',                     -- for stdio: args
    env TEXT[] DEFAULT '{}',                      -- optional env KEY=VALUE pairs
    url TEXT,                                     -- for http: endpoint URL
    api_key TEXT,                                 -- optional bearer token
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    tools_count INT NOT NULL DEFAULT 0,
    last_connected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Tools discovered from connected MCP servers.
CREATE TABLE IF NOT EXISTS mcp_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    input_schema JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (server_id, name)
);

-- Per-tool permission grants (which identities may call which tools).
CREATE TABLE IF NOT EXISTS tool_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name TEXT NOT NULL,
    identity_key TEXT NOT NULL DEFAULT '*',       -- '*' = any identity
    allowed BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tool_name, identity_key)
);

-- Indexes for the common lookups.
CREATE INDEX IF NOT EXISTS idx_mcp_servers_enabled ON mcp_servers (enabled);
CREATE INDEX IF NOT EXISTS idx_mcp_tools_server ON mcp_tools (server_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tools_enabled ON mcp_tools (enabled);
CREATE INDEX IF NOT EXISTS idx_tool_permissions_name ON tool_permissions (tool_name);

-- Auto-update updated_at on mcp_servers.
CREATE OR REPLACE FUNCTION update_mcp_servers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mcp_servers_updated_at ON mcp_servers;
CREATE TRIGGER trg_mcp_servers_updated_at
BEFORE UPDATE ON mcp_servers
FOR EACH ROW EXECUTE FUNCTION update_mcp_servers_updated_at();

NOTIFY pgrst, 'reload schema';
