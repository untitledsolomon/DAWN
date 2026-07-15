-- ──────────────────────────────────────────────────────────────────────────────
-- v40.0: Secrets Vault — encrypted credential storage
-- ──────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS secrets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    encrypted_value TEXT NOT NULL,
    description TEXT,
    tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Safely add columns if the table already existed without them
ALTER TABLE secrets ADD COLUMN IF NOT EXISTS tags TEXT[] DEFAULT '{}';
ALTER TABLE secrets ADD COLUMN IF NOT EXISTS description TEXT;

-- Index for name lookups (used by the agent at runtime)
CREATE INDEX IF NOT EXISTS idx_secrets_name ON secrets (name);

-- Index for tag filtering
CREATE INDEX IF NOT EXISTS idx_secrets_tags ON secrets USING GIN (tags);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_secrets_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_secrets_updated_at ON secrets;
CREATE TRIGGER trg_secrets_updated_at
    BEFORE UPDATE ON secrets
    FOR EACH ROW
    EXECUTE FUNCTION update_secrets_updated_at();

-- Row-level security: only service_role can access secrets
ALTER TABLE secrets ENABLE ROW LEVEL SECURITY;

-- Only allow access via the service_role API key (handled by the API middleware)
CREATE POLICY secrets_service_policy ON secrets
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
