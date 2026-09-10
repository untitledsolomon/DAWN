-- ─────────────────────────────────────────────────────────────────────────────
-- v44.0: Write-gating — approval queue for mutating tool calls.
--
-- Every mutating action (MCP tools with a create_/delete_/send_/publish_/
-- update_ prefix, and native DAWN tools marked is_mutating, e.g. send_email)
-- is queued here and requires human approval before it executes. This is the
-- safety gate that makes DAWN's "mutating actions always require approval"
-- hard requirement real.
--
-- Tool-source-agnostic by design: `server_id` is null for native tools and
-- set for MCP-routed calls, so one queue covers both paths.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pending_actions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id    UUID,                        -- MCP server id; NULL for native tools
    tool_name    TEXT NOT NULL,
    tool_args    JSONB NOT NULL DEFAULT '{}',
    requested_by TEXT,                        -- identity key of who/what requested this
    status       TEXT NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'expired', 'completed', 'failed')),
    result       JSONB,                       -- populated after execution, once approved
    error        TEXT,                        -- populated if execution failed post-approval
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at  TIMESTAMPTZ,
    resolved_by  TEXT
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_status ON pending_actions(status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_created ON pending_actions(created_at DESC);

NOTIFY pgrst, 'reload schema';
