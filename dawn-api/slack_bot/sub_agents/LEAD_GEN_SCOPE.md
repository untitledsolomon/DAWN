# Lead-Gen Sourcing Agent — Scope

## Why this is separate from crm_agent
`crm_agent` is a CRUD client for leads that already exist in the Growth
Engine (Supabase). It has no way to discover a business that isn't in that
table yet. Making DAWN "generate leads" means adding a **sourcing** step
upstream of `crm_leads.create` — a new capability, not a rewire.

## What exists today that this can reuse
- `crm_leads` tool (`operation="create"`) — already accepts
  `{name, business, email, phone, source, status, score, tags, linkedinUrl}`.
  A new source value like `"web-research"` or `"dawn-agent"` slots in without
  a schema change.
- `web_search` / `web_fetch` tools — already registered, already granted to
  `research_agent`.
- `proactive_agents.py` — already has the APScheduler wiring; a new job is a
  ~15-line addition to the `AGENTS` dict, same pattern as `scan_new_leads`.

## New tool: `lead_sourcing`
Proposed file: `tools/lead_sourcing.py`

```
operation: "find_prospects"
  input: { industry, location, count }
  → web_search + web_fetch a small set of business directories /
    LinkedIn company pages / Google Maps-style queries
  → LLM-extracts candidate {name, business, website, linkedinUrl} tuples
  → does NOT write to CRM directly — returns candidates for review
```

Deliberately **read-only** at first. It should not auto-create leads,
because unreviewed scraped contacts polluting the pipeline is worse than no
new leads. The natural flow:

1. `lead_sourcing.find_prospects` → returns N candidates to Slack
2. Human reacts 👍 in Slack (or runs `/leads approve <id>`)
3. Only then does `crm_leads.create` fire, tagged `source="dawn-sourced"`

This keeps a human in the loop for the part that's actually risky (creating
outbound targets) while automating the part that's just legwork (finding
them).

## Compliance note
Scraping LinkedIn directly violates their ToS and can get the source IP
rate-limited or banned — this is presumably *why* the existing pipeline uses
PhantomBuster (a service built to handle that risk) rather than DAWN doing
it itself. Recommend `lead_sourcing` stick to public web search / company
sites / directories, and leave LinkedIn-specific scraping to PhantomBuster
as it already does today. DAWN's role is enrichment and triage, not scraping.

## New proactive agent: `prospect_finder`
Same shape as `scan_new_leads` in `proactive_agents.py`:
- Runs daily or on a Slack-triggered `/find-leads <industry>` command
- Calls `lead_sourcing.find_prospects`
- Posts candidates as a Slack block with an "approve" button (or numbered
  list + `/leads approve N` command) rather than auto-importing

## Estimated scope
- `tools/lead_sourcing.py`: ~150 lines, same shape as `tools/crm.py`
- Register in `tools/registry.py`: 1 line
- New sub-agent `lead_sourcing_agent.yaml`: same shape as `crm_agent.yaml`
- Slack approve flow: reuse existing `/leads` command handler, add one
  branch for `approve <candidate_id>`
- No DB schema changes needed — writes through existing `crm_leads.create`

This is a half-day to one-day build, not a rewrite. The riskier and slower
part is deciding the source-quality bar (which directories/queries produce
real prospects vs. noise) — that's worth testing manually in Slack before
wiring the scheduler.
