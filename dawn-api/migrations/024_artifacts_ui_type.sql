-- Migration 024: allow 'ui' artifacts. Also fixes 'markdown' and 'note',
-- which create_artifact already produces but the CHECK in 007 rejects.
ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS artifacts_type_check;
ALTER TABLE artifacts ADD CONSTRAINT artifacts_type_check
  CHECK (type IN ('chart','table','image','file','explainer','markdown','note','ui'));
NOTIFY pgrst, 'reload schema';
