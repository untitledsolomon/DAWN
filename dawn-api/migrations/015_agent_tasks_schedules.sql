-- ──────────────────────────────────────────────────────────────────────────────
-- v42.0: Agent Tasks + Schedules tables for the autonomous-task feature.
--
-- The `agent_tasks` table used by routers/agent_tasks.py (and the dawn-ui
-- Agent Tasks page) stores long-running agent goals with progress tracking.
-- NOTE: Earlier migrations (003/009) created an `agent_tasks` table for a
-- *different* sub-agent concept (agent_name/task_type/input_data). If a
-- table with those columns already exists, this migration will NOT overwrite
-- it — drop that conflicting table first, or the router's inserts (goal,
-- parent_task_id, max_iterations, status) will fail against the wrong shape.
--
-- `agent_schedules` is brand new: it drives the background scheduler that
-- runs agent tasks autonomously on a cron/interval basis.
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

CREATE INDEX IF NOT EXISTS idx_agent_tasks_status  ON agent_tasks(status);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_created ON agent_tasks(created_at DESC);

-- Scheduled autonomous agent runs.
CREATE TABLE IF NOT EXISTS agent_schedules (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT        NOT NULL,
    task_goal       TEXT        NOT NULL,
    cron_expression TEXT        NOT NULL DEFAULT '0 * * * *',
    max_iterations  INTEGER     NOT NULL DEFAULT 50,
    enabled         BOOLEAN     NOT NULL DEFAULT TRUE,
    last_run_at     TIMESTAMPTZ,
    run_count       INTEGER     NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_schedules_enabled ON agent_schedules(enabled);

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
