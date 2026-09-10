-- ─────────────────────────────────────────────────────────────────────────────
-- v47.0: alert_events table — the AlertStrip's data source.
--
-- Referenced by routers/monitoring.py but never created; nothing ever wrote
-- to it, so the dashboard's AlertStrip showed "nothing needs attention"
-- forever. This migration creates the table and indexes it for the reads the
-- dashboard makes.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alert_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity        TEXT NOT NULL DEFAULT 'info'
                    CHECK (severity IN ('info', 'warning', 'critical')),
    title           TEXT NOT NULL,
    message         TEXT,
    source          TEXT,                        -- e.g. 'pending_actions', 'agent_tasks', 'oauth'
    source_ref      TEXT,                        -- e.g. the pending action / task id
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alert_events_severity ON alert_events(severity);
CREATE INDEX IF NOT EXISTS idx_alert_events_created ON alert_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_events_acknowledged ON alert_events(acknowledged);

NOTIFY pgrst, 'reload schema';
