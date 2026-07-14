-- ============================================================
-- DAWN Team & Projects Schema
-- Migration: 003
-- 
-- Adds team_members and projects tables to DAWN's own Supabase
-- for the Team OS layer (Phase 2).
-- ============================================================

-- Trigger helper: update updated_at on row change
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- --------------------------------------------------------
-- team_members
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_members (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  role        TEXT        NOT NULL DEFAULT 'member',
  email       TEXT,
  phone       TEXT,
  slack_id    TEXT,
  status      TEXT        NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'inactive', 'vacation')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_team_members_status ON team_members(status);
CREATE INDEX idx_team_members_role   ON team_members(role);

CREATE TRIGGER trg_team_members_updated_at
  BEFORE UPDATE ON team_members
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- --------------------------------------------------------
-- projects
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  description TEXT,
  assignee_id UUID        REFERENCES team_members(id) ON DELETE SET NULL,
  status      TEXT        NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
  priority    TEXT        NOT NULL DEFAULT 'medium'
                          CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  due_date    DATE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_projects_status      ON projects(status);
CREATE INDEX idx_projects_assignee    ON projects(assignee_id);
CREATE INDEX idx_projects_due_date    ON projects(due_date);

CREATE TRIGGER trg_projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- --------------------------------------------------------
-- deals (won/lost revenue tracking)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS deals (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name          TEXT        NOT NULL,
  client_name   TEXT        NOT NULL,
  value         NUMERIC     NOT NULL DEFAULT 0,
  currency      TEXT        NOT NULL DEFAULT 'UGX',
  status        TEXT        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'won', 'lost', 'refunded')),
  close_date    DATE,
  description   TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deals_status     ON deals(status);
CREATE INDEX idx_deals_close_date ON deals(close_date);

CREATE TRIGGER trg_deals_updated_at
  BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- --------------------------------------------------------
-- agent_tasks (for proactive agent scheduling)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_tasks (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name    TEXT        NOT NULL,
  task_type     TEXT        NOT NULL,
  schedule      TEXT        NOT NULL DEFAULT 'daily'
                          CHECK (schedule IN ('hourly', 'daily', 'weekly', 'manual')),
  config        JSONB       NOT NULL DEFAULT '{}',
  last_run      TIMESTAMPTZ,
  next_run      TIMESTAMPTZ,
  enabled       BOOLEAN     NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_tasks_enabled ON agent_tasks(enabled);
CREATE INDEX idx_agent_tasks_next_run ON agent_tasks(next_run);

CREATE TRIGGER trg_agent_tasks_updated_at
  BEFORE UPDATE ON agent_tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
