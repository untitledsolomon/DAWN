-- Dynamic Agents Table
-- Stores user-configurable proactive agents created via Slack commands.
-- Supports keyword monitors, cron reports, and threshold alerts.

CREATE TABLE IF NOT EXISTS dynamic_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK (agent_type IN ('keyword_monitor', 'cron_report', 'threshold_alert')),
    config JSONB NOT NULL DEFAULT '{}',
    channel TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'deleted')),
    created_by TEXT DEFAULT 'slack',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    last_run_at TIMESTAMPTZ,
    run_count INTEGER DEFAULT 0
);

-- Index for active agent lookups
CREATE INDEX IF NOT EXISTS idx_dynamic_agents_status ON dynamic_agents(status);
CREATE INDEX IF NOT EXISTS idx_dynamic_agents_type ON dynamic_agents(agent_type);
CREATE INDEX IF NOT EXISTS idx_dynamic_agents_channel ON dynamic_agents(channel);

-- Enable RLS
ALTER TABLE dynamic_agents ENABLE ROW LEVEL SECURITY;

-- Allow all authenticated access (DAWN is the only client)
CREATE POLICY dynamic_agents_all ON dynamic_agents
    USING (true)
    WITH CHECK (true);
