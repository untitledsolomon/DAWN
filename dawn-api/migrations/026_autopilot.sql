-- Migration 026: Autopilot jobs, runs, events. Plus the audit_log table,
-- which has no DDL anywhere in the repo though routers/audit.py reads it.

CREATE TABLE IF NOT EXISTS autopilot_jobs (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL UNIQUE,
    description          TEXT,
    goal                 TEXT NOT NULL,
    enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    autonomy             TEXT NOT NULL DEFAULT 'observe' CHECK (autonomy IN ('observe','propose')),
    schedule             JSONB,                       -- {preset:{...}, cron, timezone, active_hours:{start,end,days}, catch_up}
    triggers             JSONB NOT NULL DEFAULT '[]', -- [{event:'approval_aged', params:{}}]
    preflight            JSONB NOT NULL DEFAULT '[]', -- [{check:'aged_approvals', params:{hours:4}}]
    preflight_mode       TEXT NOT NULL DEFAULT 'any' CHECK (preflight_mode IN ('any','off')),
    tool_allowlist       TEXT[] NOT NULL DEFAULT '{}',
    model                TEXT,                        -- NULL = use llm.model
    limits               JSONB NOT NULL DEFAULT '{}', -- overrides: max_steps, max_tokens, max_seconds
    notify               JSONB NOT NULL DEFAULT '{}',
    retry                JSONB NOT NULL DEFAULT '{}',
    dedupe_hours         INTEGER NOT NULL DEFAULT 24,
    state                JSONB NOT NULL DEFAULT '{}',
    next_run_at          TIMESTAMPTZ,
    last_run_at          TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    paused_reason        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_autopilot_jobs_due ON autopilot_jobs (enabled, next_run_at);

CREATE TABLE IF NOT EXISTS autopilot_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID NOT NULL REFERENCES autopilot_jobs(id) ON DELETE CASCADE,
    triggered_by     TEXT NOT NULL CHECK (triggered_by IN ('schedule','event','manual','dry_run')),
    status           TEXT NOT NULL DEFAULT 'queued' CHECK (status IN
                     ('queued','running','quiet','completed','needs_attention','failed','budget_stopped','skipped','cancelled')),
    started_at       TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    steps            INTEGER NOT NULL DEFAULT 0,
    tokens_in        INTEGER NOT NULL DEFAULT 0,
    tokens_out       INTEGER NOT NULL DEFAULT 0,
    est_cost         NUMERIC,                        -- NULL until prices are set
    model            TEXT,
    preflight        JSONB,
    summary          TEXT,
    findings         JSONB NOT NULL DEFAULT '[]',
    tools_used       TEXT[] NOT NULL DEFAULT '{}',
    pending_action_ids UUID[] NOT NULL DEFAULT '{}',
    artifact_ids     UUID[] NOT NULL DEFAULT '{}',
    error_class      TEXT,
    error            TEXT,
    skip_reason      TEXT,
    cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
    feedback         TEXT CHECK (feedback IN ('useful','noise')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_autopilot_runs_job ON autopilot_runs (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_autopilot_runs_status ON autopilot_runs (status);

CREATE TABLE IF NOT EXISTS autopilot_events (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type         TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_autopilot_events_pending ON autopilot_events (type, created_at) WHERE processed_at IS NULL;

-- Carry old schedules over DISABLED. Nothing is auto-enabled.
INSERT INTO autopilot_jobs (name, description, goal, enabled, autonomy, schedule, limits, preflight_mode)
SELECT s.name, 'Migrated from agent_schedules', s.task_goal, FALSE, 'observe',
       jsonb_build_object('cron', s.cron_expression, 'timezone', 'Africa/Kampala', 'catch_up', 'skip'),
       jsonb_build_object('max_steps', s.max_iterations), 'off'
FROM agent_schedules s
ON CONFLICT (name) DO NOTHING;

-- One-off cleanup of rows stuck 'running' from killed processes.
UPDATE agent_tasks SET status = 'failed', error = COALESCE(error, 'server_restart')
WHERE status = 'running' AND updated_at < now() - interval '1 hour';

-- audit_log — read by routers/audit.py since forever; the DDL was never in the
-- repo, so write one that matches the columns the router reads.
CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action      TEXT NOT NULL,
    actor_type  TEXT,
    actor_ref   TEXT,
    details     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at DESC);

ALTER TABLE autopilot_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE autopilot_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE autopilot_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
NOTIFY pgrst, 'reload schema';
