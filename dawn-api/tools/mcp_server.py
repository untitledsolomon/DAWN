"""
MCP (Model Context Protocol) integration.

Two directions:
  1. DAWN connects OUT to external MCP servers (stdio or HTTP/streamable),
     discovers their tools, and exposes them to the agent.
  2. DAWN can expose its own tools via MCP (see _start_dawn_mcp_server).

Progressive discovery (Anthropic client best-practice model)
-------------------------------------------------------------
Rather than eagerly registering every discovered tool as a first-class
`mcp_<name>` DAWN tool (which blows up the model's context window past a few
dozen tools), DAWN now follows the catalog -> inspect -> execute pattern:

  * `mcp_search_tools`  -- a single lightweight meta-tool that returns the
    catalog of every connected server's tools as {server, name, description}
    (names + one-line descriptions only, no full JSON schemas).
  * `mcp_call_tool`     -- a single meta-tool that lazily connects to the
    owning server (if not already connected), fetches the full input schema
    for the requested tool, and executes it.

Individual tools are only registered as first-class `mcp_<name>` DAWN tools
when they are explicitly *pinned* (see the `pinned` column on mcp_tools). This
keeps the default context footprint tiny while still letting a user promote
their most-used remote tools to always-available.

The `mcp` Python SDK (>=1.0) is required. Connections are created lazily and
cached per server id; a connection failure returns a clear error rather than
crashing the agent loop.
"""
import asyncio
import json
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult
from tools.registry import get_registry

logger = logging.getLogger(__name__)

try:
    from mcp import Client, StdioServerParameters
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

try:
    from mcp.client.streamable_http import streamable_http_client
    HAS_HTTP_TRANSPORT = True
except ImportError:
    streamable_http_client = None  # type: ignore
    HAS_HTTP_TRANSPORT = False


def _build_http_client(bearer_token: Optional[str] = None):
    """Build an httpx.AsyncClient for an MCP streamable-HTTP connection.

    mcp >= 2.0 changed the client API: `Client` no longer accepts a
    `StreamableHTTPTransport` object (that class is not an async context
    manager in 2.x). The supported way to attach auth headers is to pass a
    pre-configured `httpx.AsyncClient` to `streamable_http_client(url,
    http_client=...)`, then hand that async context manager to `Client`.

    This returns an httpx.AsyncClient that injects an `Authorization: Bearer`
    header on every request when a token is supplied.
    """
    import httpx
    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    return httpx.AsyncClient(headers=headers, timeout=30.0)


async def _resolve_redirects(url: str) -> str:
    """Resolve an HTTP(S) redirect chain to its final URL.

    The mcp SDK's StreamableHTTPTransport refuses to follow redirects (it will
    not silently forward an Authorization header to a different host). Many
    real MCP endpoints sit behind a redirect (e.g. a bare domain that 301s to
    /api/mcp), so a connect would fail with "Redirect ... not followed".

    We resolve the chain up front with httpx (which follows redirects by
    default) and return the final URL. The transport is then built against that
    final URL, so auth headers are only ever sent to the resolved host -- never
    to an intermediate redirector. If the URL does not redirect, or resolution
    fails, the original URL is returned unchanged.
    """
    try:
        import httpx
        async with httpx.AsyncClient(follow_redirects=True) as client:
            # A lightweight GET is enough to observe the redirect chain. MCP
            # streamable HTTP servers answer POST (JSON-RPC), but a GET to the
            # endpoint will still surface any 3xx redirect before the server
            # rejects the method. We only care about the final URL, not the body.
            resp = await client.get(url)
            final_url = str(resp.url)
            if final_url and final_url != url:
                logger.info(f"MCP HTTP redirect resolved: {url} -> {final_url}")
                return final_url
    except Exception as e:
        logger.warning(f"MCP redirect resolution failed for {url}: {e}")
    return url


class MCPTool(BaseTool):
    name = "mcp"
    description = (
        "Model Context Protocol integration. Connect to external MCP servers "
        "(stdio or HTTP) to access additional tools and capabilities "
        "(databases, APIs, file systems, etc.). Also allows DAWN to expose its "
        "own tools via MCP for use by Claude Desktop and other MCP clients."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "list_servers", "connect_server", "disconnect_server",
                    "list_tools", "call_tool", "list_resources", "read_resource",
                    "start_mcp_server", "stop_mcp_server",
                ],
                "description": "The MCP operation to perform.",
            },
            "server_id": {
                "type": "string",
                "description": "ID of the MCP server in the database.",
            },
            "server_name": {
                "type": "string",
                "description": "Name of the MCP server.",
            },
            "tool_name": {
                "type": "string",
                "description": "Name of the tool to call on the remote MCP server.",
            },
            "tool_args": {
                "type": "object",
                "description": "Arguments for the tool call.",
            },
            "resource_uri": {
                "type": "string",
                "description": "URI of the resource to read.",
            },
        },
        "required": ["operation"],
    }

    def __init__(self):
        self._sessions = {}  # server_id -> mcp.Client (async context manager)
        # Register this tool as the executor for approved mutating MCP actions.
        # Native tools register a different executor (see tools/executor.py).
        from tools import pending_actions
        pending_actions.register_mcp_executor(self._execute_remote_call)

    # ── Public dispatch ──────────────────────────────────────────────────────

    async def run(
        self,
        operation: str,
        server_id: Optional[str] = None,
        server_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_args: Optional[dict] = None,
        resource_uri: Optional[str] = None,
    ) -> ToolResult:
        try:
            if operation == "list_servers":
                return await self._list_servers()
            elif operation == "connect_server":
                return await self._connect_server(server_id)
            elif operation == "disconnect_server":
                return await self._disconnect_server(server_id)
            elif operation == "list_tools":
                return await self._list_tools(server_id)
            elif operation == "call_tool":
                return await self._call_tool(server_id, tool_name, tool_args or {})
            elif operation == "list_resources":
                return await self._list_resources(server_id)
            elif operation == "read_resource":
                return await self._read_resource(server_id, resource_uri)
            elif operation == "start_mcp_server":
                return await self._start_dawn_mcp_server()
            elif operation == "stop_mcp_server":
                return await self._stop_dawn_mcp_server()
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            logger.exception(f"MCP operation failed: {e}")
            return ToolResult(success=False, error=f"MCP operation failed: {e}")

    # ── Server registry ──────────────────────────────────────────────────────

    async def _list_servers(self) -> ToolResult:
        try:
            import db.client as db
            supabase = db.get_db()
            res = await db._async_execute(lambda: supabase.table("mcp_servers").select(
                "id, name, description, server_type, enabled, tools_count, last_connected_at"
            ).eq("enabled", True).order("name").execute())
            return ToolResult(success=True, output=res.data or [])
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list servers: {e}")

    async def _get_server(self, server_id: str) -> Optional[dict]:
        import db.client as db
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_servers").select("*").eq("id", server_id).execute())
        return res.data[0] if res.data else None

    async def _connect_server(self, server_id: Optional[str]) -> ToolResult:
        """Connect to an MCP server (stdio or HTTP) and discover its tools."""
        if not server_id:
            return ToolResult(success=False, error="server_id is required")
        if not HAS_MCP:
            return ToolResult(success=False, error="MCP library not installed. Run: pip install 'mcp>=1.0.0'")

        if server_id in self._sessions:
            return ToolResult(success=True, output={"status": "already_connected", "server_id": server_id})

        server = await self._get_server(server_id)
        if not server:
            return ToolResult(success=False, error=f"Server {server_id} not found")

        server_type = server.get("server_type", "stdio")
        try:
            if server_type == "http":
                client = await self._open_http(server)
            else:
                client = await self._open_stdio(server)
            # Enter the client's async context so the connection stays alive.
            await client.__aenter__()
        except Exception as e:
            logger.warning(f"MCP connect to {server.get('name')} failed: {e}")
            # For HTTP servers, a failed connect may mean the server requires an
            # OAuth sign-in flow rather than a static key. Probe it so the UI can
            # offer a "Sign in" button instead of a dead-end error.
            requires_oauth = await self._probe_requires_oauth(server_type, server)
            return ToolResult(
                success=False,
                error=f"Failed to connect to '{server.get('name')}': {e}",
                metadata={"requires_oauth": requires_oauth},
            )

        self._sessions[server_id] = client

        # Discover and persist tools. Discovery can 401 when the server requires
        # OAuth even though the initial transport handshake succeeded (e.g. the
        # first call is unauthenticated but tools/list is gated). Probe so the UI
        # can offer a "Sign in" flow instead of a dead-end error.
        try:
            tools = await self._discover_tools(server_id, client)
        except Exception as e:
            await self._disconnect_server(server_id)
            requires_oauth = await self._probe_requires_oauth(server_type, server)
            return ToolResult(
                success=False,
                error=f"Connected but failed to discover tools: {e}",
                metadata={"requires_oauth": requires_oauth},
            )
        await self._persist_tools(server_id, tools)

        # Update last_connected_at and tools_count.
        try:
            import db.client as db
            supabase = db.get_db()
            await db._async_execute(lambda: supabase.table("mcp_servers").update({
                "last_connected_at": "now()", "tools_count": len(tools),
            }).eq("id", server_id).execute())
        except Exception as e:
            logger.warning(f"Failed to update MCP server metadata: {e}")

        return ToolResult(
            success=True,
            output={
                "status": "connected",
                "server": server["name"],
                "type": server_type,
                "tools_discovered": len(tools),
                "tools": [t["name"] for t in tools],
            },
        )

    async def _probe_requires_oauth(self, server_type: str, server: dict) -> bool:
        """Robustly determine whether an HTTP server needs OAuth.

        Runs the spec probe (401 Bearer challenge / RFC 9728 well-known metadata)
        on any HTTP connect or discovery failure -- not just when the error text
        happens to contain 'unauthorized' or '401'. The probe itself decides.
        """
        if server_type != "http":
            return False
        try:
            from tools import mcp_oauth
            if mcp_oauth.oauth_enabled():
                return bool(await mcp_oauth.probe_oauth(server.get("url") or ""))
        except Exception:
            pass
        return False

    async def check_oauth_status(self, server_id: str) -> bool:
        """Proactively probe whether a server requires OAuth (no connect needed).

        Used by the UI's add/connect flow so it can launch the consent popup
        immediately instead of doing a doomed unauthenticated connect first.
        """
        server = await self._get_server(server_id)
        if not server:
            return False
        if server.get("server_type") != "http":
            return False
        return await self._probe_requires_oauth("http", server)

    async def _open_stdio(self, server: dict) -> Client:
        params = StdioServerParameters(
            command=server.get("command") or "",
            args=server.get("args") or [],
            env=dict(e.split("=", 1) for e in (server.get("env") or []) if "=" in e) or None,
        )
        return Client(params)

    async def _open_http(self, server: dict) -> Client:
        url = server.get("url")
        if not url:
            raise ValueError("HTTP MCP server requires a 'url'")
        # Resolve any redirect chain up front. The mcp SDK transport refuses to
        # follow redirects, so we point it at the final URL instead. Auth headers
        # are then only ever sent to the resolved host.
        url = await _resolve_redirects(url)
        server_id = server.get("id")
        bearer = None
        # OAuth-authenticated server — use the stored access token (refreshing
        # if needed) as the bearer instead of a static API key.
        if server_id:
            try:
                from tools import mcp_oauth
                if mcp_oauth.oauth_enabled():
                    is_oauth_server = await mcp_oauth.has_oauth_tokens(server_id)
                    if is_oauth_server:
                        access_token = await mcp_oauth.get_access_token(server_id)
                        if not access_token:
                            raise RuntimeError(
                                "OAuth token unavailable or refresh failed for this "
                                "server — re-authenticate via the Sign in flow."
                            )
                        bearer = access_token
            except Exception as e:
                logger.warning(f"Failed to load OAuth token for MCP server {server_id}: {e}")
                raise  # don't silently fall through to api_key for an OAuth-only server
        if not bearer:
            bearer = server.get("api_key")
        if not HAS_HTTP_TRANSPORT:
            raise RuntimeError("MCP streamable-HTTP transport not available")
        # mcp >= 2.0: build an authenticated httpx client and hand it to
        # streamable_http_client, then wrap that async context manager in Client.
        # (Client(AuthStreamableHTTPTransport(...)) no longer works in 2.x.)
        http_client = _build_http_client(bearer)
        return Client(streamable_http_client(url, http_client=http_client))

    async def _discover_tools(self, server_id: str, client: Client) -> list[dict]:
        result = await client.list_tools()
        tools = []
        for t in result.tools:
            tools.append({
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.input_schema or {"type": "object", "properties": {}},
            })
        return tools

    async def _persist_tools(self, server_id: str, tools: list[dict]) -> None:
        """Upsert discovered tools into mcp_tools.

        Under progressive discovery, tools are persisted to the catalog but NOT
        auto-registered as first-class DAWN tools. Only tools already marked
        `pinned` in the DB are (re)registered eagerly. This keeps the model's
        context footprint small; the catalog is reachable via `mcp_search_tools`
        and execution via `mcp_call_tool`.
        """
        if not tools:
            return
        import db.client as db
        supabase = db.get_db()
        for t in tools:
            await db._async_execute(lambda t=t: supabase.table("mcp_tools").upsert({
                "server_id": server_id,
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
                "enabled": True,
            }, on_conflict="server_id,name").execute())
        # Register only tools that are already pinned (so a re-connect keeps a
        # user's pinned tools available without re-registering everything).
        registry = get_registry()
        for t in tools:
            if await self._is_pinned(server_id, t["name"]):
                self._register_remote_tool(registry, server_id, t)

    async def _is_pinned(self, server_id: str, tool_name: str) -> bool:
        try:
            import db.client as db
            supabase = db.get_db()
            res = await db._async_execute(lambda: supabase.table("mcp_tools").select(
                "pinned"
            ).eq("server_id", server_id).eq("name", tool_name).maybe_single().execute())
            return bool(res.data and res.data.get("pinned"))
        except Exception:
            return False

    def _register_remote_tool(self, registry, server_id: str, t: dict) -> None:
        """Register a single remote tool as a first-class DAWN tool (pinned)."""
        name = t["name"]
        if registry.get(f"mcp_{name}"):
            return
        try:
            registry.register(RemoteMCPTool(
                server_id,
                name,
                t.get("description") or name,
                t.get("input_schema") or {"type": "object", "properties": {}},
            ))
        except Exception as e:
            logger.warning(f"Failed to register pinned MCP tool '{name}': {e}")

    async def _disconnect_server(self, server_id: Optional[str]) -> ToolResult:
        client = self._sessions.pop(server_id, None)
        if client:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        return ToolResult(success=True, output={"status": "disconnected"})

    # ── Tools / resources ────────────────────────────────────────────────────

    async def _list_tools(self, server_id: Optional[str]) -> ToolResult:
        if not server_id:
            return ToolResult(success=False, error="server_id is required")
        try:
            import db.client as db
            supabase = db.get_db()
            res = await db._async_execute(lambda: supabase.table("mcp_tools").select(
                "name, description, input_schema"
            ).eq("server_id", server_id).eq("enabled", True).order("name").execute())
            return ToolResult(success=True, output=res.data or [])
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list tools: {e}")

    async def _call_tool(self, server_id: Optional[str], tool_name: Optional[str], args: dict) -> ToolResult:
        if not server_id or not tool_name:
            return ToolResult(success=False, error="server_id and tool_name are required")
        if not HAS_MCP:
            return ToolResult(success=False, error="MCP library not installed")

        # Write-gating: mutating tools are queued for human approval instead of
        # executing immediately. Read-only tools continue straight through.
        from tools.pending_actions import is_mutating_tool, queue_pending_action
        if is_mutating_tool(tool_name):
            return await queue_pending_action(server_id, tool_name, args)

        return await self._execute_remote_call(server_id, tool_name, args)

    async def _execute_remote_call(self, server_id: str, tool_name: str, args: dict) -> ToolResult:
        """Shared execution path for a remote MCP tool call.

        Used by both the read-only path in `_call_tool` and by the approval
        execution path (`execute_pending_action`), so there is exactly one code
        path that actually talks to the MCP server.
        """
        client = self._sessions.get(server_id)
        if client is None:
            # Try connecting on demand.
            connect = await self._connect_server(server_id)
            if not connect.success:
                return connect
            client = self._sessions.get(server_id)
        if client is None:
            return ToolResult(success=False, error=f"Server {server_id} is not connected")

        try:
            result = await client.call_tool(tool_name, args)
        except Exception as e:
            return ToolResult(success=False, error=f"MCP tool '{tool_name}' failed: {e}")

        if getattr(result, "is_error", False):
            return ToolResult(success=False, error=f"MCP tool '{tool_name}' returned an error")

        # Serialize content blocks (usually TextContent).
        text_parts = []
        for block in getattr(result, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
            else:
                text_parts.append(str(block))
        output = "\n".join(text_parts) if text_parts else None
        if output is None and getattr(result, "structured_content", None) is not None:
            output = result.structured_content

        return ToolResult(success=True, output=output, metadata={"mcp_tool": tool_name})

    async def _list_resources(self, server_id: Optional[str]) -> ToolResult:
        if not server_id:
            return ToolResult(success=False, error="server_id is required")
        client = self._sessions.get(server_id)
        if client is None:
            return ToolResult(success=False, error=f"Server {server_id} is not connected")
        try:
            result = await client.list_resources()
            resources = [
                {"uri": r.uri, "name": getattr(r, "name", ""), "description": getattr(r, "description", "")}
                for r in result.resources
            ]
            return ToolResult(success=True, output=resources)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list resources: {e}")

    async def _read_resource(self, server_id: Optional[str], resource_uri: Optional[str]) -> ToolResult:
        if not server_id or not resource_uri:
            return ToolResult(success=False, error="server_id and resource_uri are required")
        client = self._sessions.get(server_id)
        if client is None:
            return ToolResult(success=False, error=f"Server {server_id} is not connected")
        try:
            result = await client.read_resource(resource_uri)
            return ToolResult(success=True, output=result.contents)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read resource: {e}")

    # ── Expose DAWN's own tools via MCP ──────────────────────────────────────

    async def _start_dawn_mcp_server(self) -> ToolResult:
        """Start DAWN's own MCP server so external MCP clients (Claude Desktop,
        Cursor, etc.) can use DAWN's tools.

        Handles both mcp v1 (FastMCP) and mcp v2 (MCPServer) APIs.
        """
        registry = get_registry()
        tools = [t for t in registry.list_tools()
                 if t.name not in ("mcp", "install_skill", "install_ecc_skill")]

        # mcp v2: MCPServer with add_tool.
        try:
            from mcp.server.mcpserver import MCPServer
            server = MCPServer("DAWN")
            for tool in tools:
                try:
                    server.add_tool(
                        _make_tool_wrapper(tool),
                        name=tool.name,
                        description=tool.description,
                    )
                except Exception as e:
                    logger.warning(f"Failed to expose tool '{tool.name}' via MCP: {e}")
            self._mcp_server = server
            return ToolResult(
                success=True,
                output={
                    "status": "started",
                    "note": (
                        "DAWN MCP server is available (mcp v2). Run it as a "
                        "stdio server and point your MCP client at it."
                    ),
                    "tools_exposed": len(tools),
                },
            )
        except ImportError:
            pass

        # mcp v1: FastMCP with .tool().
        try:
            from mcp.server.fastmcp import FastMCP
            server = FastMCP("DAWN")
            for tool in tools:
                try:
                    server.tool(name=tool.name, description=tool.description)(
                        _make_tool_wrapper(tool)
                    )
                except Exception as e:
                    logger.warning(f"Failed to expose tool '{tool.name}' via MCP: {e}")
            self._mcp_server = server
            return ToolResult(
                success=True,
                output={
                    "status": "started",
                    "note": (
                        "DAWN MCP server is available (mcp v1). Run it as a "
                        "stdio server and point your MCP client at it."
                    ),
                    "tools_exposed": len(tools),
                },
            )
        except ImportError:
            return ToolResult(success=False, error="MCP server library not available")

    async def _stop_dawn_mcp_server(self) -> ToolResult:
        self._mcp_server = None
        return ToolResult(success=True, output={"status": "stopped"})


def _make_tool_wrapper(tool: BaseTool):
    """Build an MCP tool handler that calls a DAWN registry tool."""
    import inspect

    async def handler(**kwargs):
        result = await tool.run(**kwargs)
        if not result.success:
            raise ValueError(result.error or "Tool failed")
        return result.output

    # Attach the input schema from the underlying tool.
    handler.__mcp_input_schema__ = tool.input_schema
    handler.__name__ = tool.name
    return handler


# ── Progressive discovery: catalog + lazy execution meta-tools ──────────────
# These two tools are the ONLY MCP surface the agent sees by default. They keep
# the model's context footprint tiny regardless of how many servers/tools are
# connected, matching Anthropic's client best-practice pattern:
#   catalog (names + one-liners) -> inspect (full schema on demand) -> execute.


class MCPCatalogTool(BaseTool):
    """Search the catalog of tools exposed by connected MCP servers.

    Returns lightweight entries ({server, name, description}) across every
    enabled server. Use this to discover what remote tools are available before
    calling one. To execute a tool, use mcp_call_tool.
    """
    name = "mcp_search_tools"
    description = (
        "Search the catalog of tools exposed by connected MCP servers. Returns "
        "lightweight {server, name, description} entries across all enabled "
        "servers. Use this to discover what remote tools are available, then "
        "call one with mcp_call_tool."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional substring to filter tool names/descriptions by.",
            },
            "server_id": {
                "type": "string",
                "description": "Optional server id to restrict the search to.",
            },
        },
    }

    async def run(self, query: Optional[str] = None, server_id: Optional[str] = None) -> ToolResult:
        try:
            import db.client as db
            supabase = db.get_db()
            q = supabase.table("mcp_tools").select(
                "name, description, server_id, mcp_servers(name)"
            ).eq("enabled", True)
            if server_id:
                q = q.eq("server_id", server_id)
            res = await db._async_execute(lambda: q.order("name").execute())
            rows = res.data or []
            results = []
            for r in rows:
                name = r.get("name") or ""
                desc = (r.get("description") or "").strip()
                if query:
                    ql = query.lower()
                    if ql not in name.lower() and ql not in desc.lower():
                        continue
                server_name = (r.get("mcp_servers") or {}).get("name") if isinstance(r.get("mcp_servers"), dict) else None
                results.append({
                    "server_id": r.get("server_id"),
                    "server": server_name or r.get("server_id"),
                    "name": name,
                    "description": desc,
                })
            return ToolResult(success=True, output=results)
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to search MCP tools: {e}")


class MCPCallTool(BaseTool):
    """Call a tool on a connected MCP server by name.

    Lazily connects to the owning server if needed, then executes the remote
    tool with the given arguments. Use mcp_search_tools first to find the
    server_id and tool name.
    """
    name = "mcp_call_tool"
    description = (
        "Call a tool exposed by a connected MCP server. Provide the server_id "
        "and tool name (find them with mcp_search_tools) plus the arguments the "
        "tool expects. Connects to the server on demand if it is not already "
        "connected."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "server_id": {
                "type": "string",
                "description": "ID of the MCP server that owns the tool.",
            },
            "tool_name": {
                "type": "string",
                "description": "Name of the remote tool to call.",
            },
            "tool_args": {
                "type": "object",
                "description": "Arguments to pass to the remote tool.",
            },
        },
        "required": ["server_id", "tool_name"],
    }

    async def run(self, server_id: str, tool_name: str, tool_args: Optional[dict] = None) -> ToolResult:
        if not server_id or not tool_name:
            return ToolResult(success=False, error="server_id and tool_name are required")
        # Route through the shared MCPTool instance so connections are reused.
        mcp_tool = next((t for t in get_registry().list_tools() if t.name == "mcp"), None)
        if mcp_tool is None:
            return ToolResult(success=False, error="MCP tool not available")
        return await mcp_tool._call_tool(server_id, tool_name, tool_args or {})


async def load_persisted_mcp_tools() -> int:
    """Load the MCP surface into the registry at startup.

    Under progressive discovery this registers ONLY:
      1. the two meta-tools (mcp_search_tools, mcp_call_tool), and
      2. any tools explicitly pinned by the user (mcp_<name>).

    It does NOT eagerly register every discovered tool -- that would blow up the
    model's context window as servers accumulate. Returns the number of
    first-class tools registered (pinned tools only; meta-tools are not counted).
    """
    registry = get_registry()

    # 1. Always ensure the two meta-tools are present.
    if registry.get("mcp_search_tools") is None:
        try:
            registry.register(MCPCatalogTool())
        except Exception as e:
            logger.warning(f"Failed to register mcp_search_tools: {e}")
    if registry.get("mcp_call_tool") is None:
        try:
            registry.register(MCPCallTool())
        except Exception as e:
            logger.warning(f"Failed to register mcp_call_tool: {e}")

    # 2. Load only pinned tools as first-class DAWN tools.
    try:
        import db.client as db
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_tools").select(
            "server_id, name, description, input_schema"
        ).eq("enabled", True).eq("pinned", True).execute())
    except Exception as e:
        logger.warning(f"Failed to load persisted MCP tools: {e}")
        return 0

    count = 0
    for t in res.data or []:
        name = t.get("name")
        server_id = t.get("server_id")
        if not name or not server_id:
            continue
        if registry.get(f"mcp_{name}"):
            continue  # already registered
        try:
            registry.register(RemoteMCPTool(
                server_id,
                name,
                t.get("description") or name,
                t.get("input_schema") or {"type": "object", "properties": {}},
            ))
            count += 1
        except Exception as e:
            logger.warning(f"Failed to register persisted MCP tool '{name}': {e}")
    if count:
        logger.info(f"Loaded {count} pinned MCP tool(s) into the registry")
    return count


class RemoteMCPTool(BaseTool):
    """A tool discovered from an external MCP server, registered into DAWN's
    registry so the agent can call it directly (name: 'mcp_<tool_name>').

    Only tools explicitly pinned by the user are registered this way. All other
    discovered tools live in the catalog and are reached via mcp_call_tool.
    """

    def __init__(self, server_id: str, name: str, description: str, input_schema: dict):
        self._server_id = server_id
        self._remote_name = name
        self.name = f"mcp_{name}"
        self.description = f"[MCP:{server_id[:8]}] {description or name}"
        self.input_schema = input_schema or {"type": "object", "properties": {}}

    async def run(self, **kwargs) -> ToolResult:
        # Route through the shared MCPTool instance so connections are reused.
        from tools.registry import get_registry
        mcp_tool = next((t for t in get_registry().list_tools() if t.name == "mcp"), None)
        if mcp_tool is None:
            return ToolResult(success=False, error="MCP tool not available")
        return await mcp_tool._call_tool(self._server_id, self._remote_name, kwargs)
