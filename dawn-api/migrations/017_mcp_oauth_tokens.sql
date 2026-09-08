-- ──────────────────────────────────────────────────────────────────────────────
-- v43.0: MCP OAuth tokens — stores OAuth 2.1 (MCP Authorization spec) tokens
-- for HTTP MCP servers that require a browser sign-in flow instead of a static
-- API key. One row per server (matches DAWN's model of one connection = one
-- server). Referenced by tools/mcp_oauth.py and routers/mcp.py.
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mcp_oauth_tokens (
    server_id UUID PRIMARY KEY REFERENCES mcp_servers(id) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    expires_at TIMESTAMPTZ,
    client_id TEXT,
    client_secret TEXT,
    token_endpoint TEXT,
    token_endpoint_auth_method TEXT,
    scope TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mcp_oauth_tokens_server ON mcp_oauth_tokens (server_id);

-- Auto-update updated_at on mcp_oauth_tokens.
CREATE OR REPLACE FUNCTION update_mcp_oauth_tokens_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mcp_oauth_tokens_updated_at ON mcp_oauth_tokens;
CREATE TRIGGER trg_mcp_oauth_tokens_updated_at
BEFORE UPDATE ON mcp_oauth_tokens
FOR EACH ROW EXECUTE FUNCTION update_mcp_oauth_tokens_updated_at();

NOTIFY pgrst, 'reload schema';
