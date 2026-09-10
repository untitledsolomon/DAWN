# VAULT INDEX

Read this at the start of every conversation. It holds the profile of the
person DAWN works for and the map of this vault.

## Who I Am

Solomon — founder of Regent, a Kampala-based firm positioned as a "mini
Palantir" for East African SMEs, serving real clients across Uganda and
South Sudan. Building DAWN as an internal AI agent ops command center
overseeing two domains: Axis (infrastructure/systems) and Regent
(marketing/business platform). Stack: FastAPI (dawn-api), Next.js 14
(dawn-ui), Supabase, DeepSeek.

North star for DAWN: a functional assistant, not a demo — one that adapts
to my workflow, surfaces what needs attention, and acts autonomously on
read-only/diagnostic work while gating anything mutating behind approval.

## Vault Structure

```
00 - Inbox          ← Capture everything, sort later
01 - Daily Notes    ← Dated logs of what got done, one file per day
Projects            ← Project knowledge (DAWN, Regent ops, etc.)
Personal            ← Life outside work
Archive             ← Completed projects and old notes
Resources           ← Cross-project reference material
```

## What's Active Right Now

- MCP OAuth 2.1 PR review (regent-website-mcp): plaintext token storage and
  missing `_pending_flows` TTL are confirmed issues; `_open_http` fallback
  behavior review still pending.
- Tool cleanup: removing Forge, CRM, and Axis custom tools (replaced by MCP
  servers) and the unused pentest auto-scheduler (tools/scheduler.py).
  Pentest/OSINT/nmap/ssh tools themselves are staying — only the scheduler
  goes.
- Memory pipeline efficiency fixes: gating background memory extraction and
  recall so they don't run unconditionally on every message — this was
  driving up DeepSeek API costs.
- No autonomous schedules are running yet (agent_schedules table is empty)
  — the runner (tools/agent_scheduler.py) exists but nothing has been
  seeded. No schedule UI exists in dawn-ui yet either; backend CRUD
  (/agent-schedules) is ready and unused.

Keep this section short — it's loaded in full on every single message, so
it should stay a snapshot of current priorities, not a running log. Move
anything that becomes historical into a dated note under 01 - Daily Notes
or the relevant file under Projects instead of leaving it here.
