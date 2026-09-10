-- ─────────────────────────────────────────────────────────────────────────────
-- v48.0: Store the final result/report of an agent task.
--
-- Previously agent_tasks had no column for the task's final output, so a
-- completed task showed only its goal and status — no report, no way to follow
-- up. This adds `result` (the final agent response) and `error` (failure
-- detail), and `follow_up` (a follow-up prompt for the task).
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS result TEXT;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS follow_up TEXT;

NOTIFY pgrst, 'reload schema';
