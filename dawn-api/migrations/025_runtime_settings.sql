-- Migration 025: runtime settings (overrides only; defaults live in the registry).
CREATE TABLE IF NOT EXISTS runtime_settings (
    key         TEXT PRIMARY KEY,
    value       JSONB NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    updated_by  TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runtime_settings_history (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    key         TEXT NOT NULL,
    old_value   JSONB,
    new_value   JSONB,        -- NULL means "reset to default"
    changed_by  TEXT,
    reason      TEXT,
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rs_history_key ON runtime_settings_history (key, changed_at DESC);

-- Atomic write + history in one call (Supabase REST has no multi-statement transactions).
CREATE OR REPLACE FUNCTION set_runtime_setting(p_key TEXT, p_value JSONB, p_by TEXT, p_reason TEXT)
RETURNS runtime_settings AS $$
DECLARE old_val JSONB; result_row runtime_settings;
BEGIN
    SELECT value INTO old_val FROM runtime_settings WHERE key = p_key;
    IF p_value IS NULL THEN
        DELETE FROM runtime_settings WHERE key = p_key;
        INSERT INTO runtime_settings_history (key, old_value, new_value, changed_by, reason)
        VALUES (p_key, old_val, NULL, p_by, p_reason);
        RETURN NULL;
    END IF;
    INSERT INTO runtime_settings (key, value, version, updated_by, updated_at)
    VALUES (p_key, p_value, 1, p_by, now())
    ON CONFLICT (key) DO UPDATE
        SET value = EXCLUDED.value, version = runtime_settings.version + 1,
            updated_by = EXCLUDED.updated_by, updated_at = now()
    RETURNING * INTO result_row;
    INSERT INTO runtime_settings_history (key, old_value, new_value, changed_by, reason)
    VALUES (p_key, old_val, p_value, p_by, p_reason);
    RETURN result_row;
END; $$ LANGUAGE plpgsql;

ALTER TABLE runtime_settings ENABLE ROW LEVEL SECURITY;          -- service role only, like `secrets`
ALTER TABLE runtime_settings_history ENABLE ROW LEVEL SECURITY;

-- S2: the `settings` table has no DDL in the repo though routers/settings.py
-- reads and writes it. Add it so a fresh database matches. It stays for UI
-- preferences only (theme, font size); runtime tunables live above.
CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       JSONB,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

NOTIFY pgrst, 'reload schema';
