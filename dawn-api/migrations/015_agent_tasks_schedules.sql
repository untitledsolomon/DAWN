-- ──────────────────────────────────────────────────────────────────────────────
-- v42.0: Agent Tasks + Schedules tables for the autonomous-task feature.
--
-- `agent_tasks` stores long-running agent goals with progress tracking.
-- `agent_schedules` drives the background scheduler that runs agent tasks
-- autonomously on an interval basis.
--
-- Both tables may already exist in the live DB with a slightly different shape
-- (e.g. agent_schedules historically used `is_active` / `next_run_at`). This
-- migration is idempotent: it adds any missing columns and indexes rather than
-- recreating the tables, so it's safe to run against an existing deployment.
-- ──────────────────────────────────────────────────────────────────────────────

-- Long-running agent tasks (goal + progress + status).
CREATE TABLE IF NOT EXISTS agent_tasks (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    goal            TEXT        NOT NULL,
    parent_task_id  UUID,
    max_iterations  INTEGER     NOT NULL DEFAULT 100,
    progress        NUMERIC     NOT NULL DEFAULT 0,
    iterations      INTEGER     NOT NULL DEFAULT 0,
    tools_used      JSONB       DEFAULT '[]',
    status          TEXT        NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add any missing agent_tasks columns (idempotent).
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS progress NUMERIC NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS iterations INTEGER NOT NULL DEFAULT 0;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS tools_used JSONB DEFAULT '[]';
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status  ON agent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_created ON agent_tasks(created_at DESC);

-- Scheduled autonomous agent runs.
CREATE TABLE IF NOT EXISTS agent_schedules (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    task_goal       TEXT        NOT NULL,
    cron_expression TEXT        NOT NULL DEFAULT '0 * * * *',
    max_iterations  INTEGER     NOT NULL DEFAULT 50,
    is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Align an existing agent_schedules table to this schema (idempotent).
ALTER TABLE agent_schedules ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agent_schedules ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMPTZ;
ALTER TABLE agent_schedules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_agent_schedules_active ON agent_schedules(is_active);

-- Auto-update updated_at on both tables.
CREATE OR REPLACE FUNCTION update_agent_tasks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_tasks_updated_at ON agent_tasks;
CREATE TRIGGER trg_agent_tasks_updated_at
BEFORE UPDATE ON agent_tasks
FOR EACH ROW EXECUTE FUNCTION update_agent_tasks_updated_at();

DROP TRIGGER IF EXISTS trg_agent_schedules_updated_at ON agent_schedules;
CREATE TRIGGER trg_agent_schedules_updated_at
BEFORE UPDATE ON agent_schedules
FOR EACH ROW EXECUTE FUNCTION update_agent_tasks_updated_at();

NOTIFY pgrst, 'reload schema';
