# DAWN MCP stdio env inheritance fix

**Date:** 2026 (current session)
**Commit (sandbox clone):** `8f5f5fb8`
**File:** `dawn-api/tools/mcp_server.py` → `_open_stdio`

## Problem
`_open_stdio` built the child MCP server process env **only** from the server
row's `env` field. Shell/service-set variables (PATH, `*_KEY`, `*_TOKEN`,
`*_CLIENT_SECRETS_FILE`) never reached the spawned stdio MCP server, because
DAWN may be launched from an environment that differs from what a bare DB row
can express.

**Concrete failure:** Google Search Console MCP server (`AminForou/mcp-gsc`)
failed auth even though `GSC_OAUTH_CLIENT_SECRETS_FILE` was set in the
launching shell. The `reauthenticate` tool returned "OAuth client secrets file
not found" because the child process never inherited the var.

## Fix
```python
async def _open_stdio(self, server: dict) -> Client:
    import os
    env = dict(os.environ)                      # inherit parent env
    for e in (server.get("env") or []):         # then apply per-server overrides
        if "=" in e:
            key, _, value = e.partition("=")
            env[key] = value
    params = StdioServerParameters(
        command=server.get("command") or "",
        args=server.get("args") or [],
        env=env,
    )
    return Client(params)
```
Row `env` entries take precedence over inherited parent env.

## Status
- ✅ Committed to sandbox clone (`8f5f5fb8`), file compiles clean.
- ⚠️ **Must be ported to the LIVE project** at
  `D:\Projects\DAWN\dawn-api\dawn-api\tools\mcp_server.py`, then DAWN restarted.

## Bigger design gap (deferred)
Solomon noted env vars don't scale across machines or multiple servers, and a
local file path is meaningless on a remote server. The proper fix is per-server
config storage that isn't a local env var — e.g. store credentials/secrets
against the server row (or a secrets store) so the same server config works on
any host. To be designed and implemented later.
