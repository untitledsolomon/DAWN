-- ============================================================
-- DAWN v3.2.0 — Team, Projects, Deals, and Agent Tasks tables
-- ============================================================

-- -----------------------------------------------------------
-- team_members
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_members (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT        NOT NULL,
    role        TEXT        NOT NULL DEFAULT 'member',
    email       TEXT,
    phone       TEXT,
    slack_id    TEXT,
    avatar_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_team_members_role ON team_members(role);

CREATE TRIGGER trg_team_members_updated_at
    BEFORE UPDATE ON team_members
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------
-- projects
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    description   TEXT,
    assignee_id   UUID        REFERENCES team_members(id) ON DELETE SET NULL,
    assignee_name TEXT,
    status        TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
    priority      TEXT        DEFAULT 'medium'
                              CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    due_date      DATE,
    tags          TEXT[]      NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_projects_status      ON projects(status);
CREATE INDEX idx_projects_assignee    ON projects(assignee_id);
CREATE INDEX idx_projects_due_date    ON projects(due_date);

CREATE TRIGGER trg_projects_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------
-- deals
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS deals (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT        NOT NULL,
    client_name   TEXT        NOT NULL,
    value         NUMERIC     NOT NULL DEFAULT 0 CHECK (value >= 0),
    status        TEXT        NOT NULL DEFAULT 'negotiation'
                              CHECK (status IN ('prospecting', 'negotiation', 'proposal', 'won', 'lost')),
    close_date    DATE,
    notes         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deals_status ON deals(status);
CREATE INDEX idx_deals_value  ON deals(value DESC);

CREATE TRIGGER trg_deals_updated_at
    BEFORE UPDATE ON deals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- -----------------------------------------------------------
-- agent_tasks (for tracking what sub-agents are doing)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_tasks (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name    TEXT        NOT NULL,
    task_type     TEXT        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    input_data    JSONB,
    output_data   JSONB,
    error_message TEXT,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_tasks_agent   ON agent_tasks(agent_name);
CREATE INDEX idx_agent_tasks_status  ON agent_tasks(status);
CREATE INDEX idx_agent_tasks_created ON agent_tasks(created_at DESC);
