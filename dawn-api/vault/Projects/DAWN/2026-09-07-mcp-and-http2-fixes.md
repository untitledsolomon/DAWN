# DAWN API — MCP import crash + Supabase HTTP/2 500 fixes

Date: 2026-09-07. Applied to the LIVE project at `D:\Projects\DAWN\dawn-api\`
(the running server). Note: the sandbox git clone at
`D:\Projects\DAWN\dawn-api\sandbox\DAWN\` is a SEPARATE copy — fixes must be
applied to the live project, not just the clone.

## Issue 1 — `GET /nodes/memory/pending` intermittent 500
`httpcore.LocalProtocolError: Invalid input StreamInputs.SEND_DATA in state 5`

Root cause: supabase-py 2.4.6 hardcodes `http2=True` on its underlying httpx
client (`postgrest._sync.client.SyncPostgrestClient.create_session`). HTTP/2
connection reuse against Supabase's proxy intermittently fails when a pooled
connection is closed/reset server-side. Transient, not a query bug.

Fix in `db/client.py`: `_async_execute` now retries (2 attempts) on
`httpx` connection-level errors (`LocalProtocolError`, `RemoteProtocolError`,
`ConnectError`, `ReadError`, `WriteError`, timeouts, `TransportError`),
dropping stale pooled connections via `_drop_stale_connections()` between
attempts (closes `get_db().postgrest.session` and the CC client session).
httpx clients are reusable after `close()`.

## Issue 2 — MCP connect 500 `name 'Client' is not defined`
Every MCP endpoint 500'd because `tools/mcp_server.py` could not import.

Root cause: the code did `from mcp import Client, StdioServerParameters`, but
the installed mcp was **1.1.3**, which has no top-level `Client` (only
`ClientSession`). The guarded import failed → `Client` never bound → eager
evaluation of `-> Client` annotations on `_open_stdio`/`_open_http` raised
`NameError` at module import.

Fix (two parts):
1. **Upgraded mcp 1.1.3 → 1.9.4** (`pip install mcp==1.9.4`). 1.9.4 has
   `streamable_http` (HTTP MCP) + `FastMCP` (DAWN-as-server) while keeping
   `httpx==0.27.0` and `uvicorn==0.29.0` (no conflict with pinned deps).
   Collateral: `pydantic-settings` 2.2.1 → 2.15.0 (config verified OK).
2. **Rewrote `tools/mcp_server.py` to be version-adaptive**:
   - Added `from __future__ import annotations` (annotations never crash import).
   - Detects mcp API: top-level `Client` (newer) vs `ClientSession` +
     `stdio_client`/`sse_client` (older).
   - New `_MCPConnection` holder keeps transport + session alive together.
   - `_open_stdio`: `Client(params)` (new) or `stdio_client`+`ClientSession` (old).
   - `_open_http`: `Client(StreamableHTTPTransport)` (new) or
     `streamablehttp_client`+`ClientSession` (1.9.x), with `httpx.BearerAuth`
     for api_key. Preserved `AuthStreamableHTTPTransport` for newer mcp.
   - Preserved local edits: `AuthStreamableHTTPTransport`, `load_persisted_mcp_tools`.

## Requirements.txt note (NOT changed — user decision needed)
Live `requirements.txt` declares `mcp>=2.0.0,<3.0.0` but ALSO pins
`httpx==0.27.0` and `uvicorn==0.29.0`. mcp 2.x is a major rewrite (uses
`httpx2`, `mcp-types`, opentelemetry, needs uvicorn>=0.31.1) — inconsistent
with the httpx 0.27 pin. Installed 1.9.4 instead (safe, matches code API,
keeps httpx 0.27). If the user wants mcp 2.x, that's a deliberate migration
(update httpx/uvicorn pins too). requirements.txt is now out of sync with the
installed mcp (1.9.4) and pydantic-settings (2.15.0).

## Verification
- `import main` (full FastAPI app) succeeds.
- `tools.mcp_server` imports: HAS_MCP=True, HAS_SESSION_API=True,
  HAS_HTTP_TRANSPORT=True on mcp 1.9.4.
- stdio + HTTP connection paths wired and reach the transport/initialize stage
  (subprocess/network failures in tests were due to dead test targets, not code).
