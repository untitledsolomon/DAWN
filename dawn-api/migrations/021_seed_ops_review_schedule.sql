-- ─────────────────────────────────────────────────────────────────────────────
-- v46.0: Seed the first autonomous schedule — "Ops review".
--
-- Runs a few times a day during a working window and reviews the state of
-- Regent and Axis operations, flagging anything that needs Solomon's
-- attention. Allowed to take mutating actions, which queue for approval via
-- the write-gating system (pending_actions).
--
-- This is the capstone of the autonomy work — the first real end-to-end
-- exercise of write-gating, memory efficiency, and the vault index.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO agent_schedules (name, task_goal, cron_expression, max_iterations, is_active)
SELECT
  'Ops review',
  $goal$
Review the current state of Regent and Axis operations and decide if
anything needs Solomon's attention or action right now.

Steps:
1. Check the vault index (vault_read on VAULT-INDEX.md, or the
   knowledge_graph tool) for current priorities and active work — ground
   everything below in what Solomon has said actually matters right now,
   not a generic checklist.
2. Check for anything already flagged as needing attention: unresolved
   alerts (if the alerting system has entries), pending approvals sitting
   unresolved for more than a few hours, and any agent_tasks that failed
   since the last run.
3. Within the domains noted as active in the vault index, do read-only
   investigation relevant to what's actually flagged as in-progress —
   don't invent work outside what's in scope right now. If nothing is
   flagged as active, do nothing further and say so plainly rather than
   fabricating busywork.
4. If something genuinely needs Solomon's decision or action, say so
   clearly and specifically — not "things look fine" as a default, and
   not manufactured urgency either. If a mutating action would help
   (e.g. drafting a response, opening a PR, sending a status update),
   take it — it will queue for approval automatically, so proposing it
   is safe.
5. If nothing needs attention, say that plainly and stop. A short "all
   quiet" result is a completely valid outcome — do not pad it with
   speculative busywork just to have something to report.

Be concrete: name specific things (which PR, which alert, which task),
not vague summaries. This runs unattended several times a day — Solomon
will only read this if it's worth reading.
$goal$,
  '0 8,12,16,20 * * *',  -- 8am, noon, 4pm, 8pm — adjust to Solomon's working hours
  30,
  true
WHERE NOT EXISTS (
  SELECT 1 FROM agent_schedules WHERE name = 'Ops review'
);

NOTIFY pgrst, 'reload schema';
