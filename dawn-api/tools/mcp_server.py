"""
MCP (Model Context Protocol) integration.

Two directions:
  1. DAWN connects OUT to external MCP servers (stdio or HTTP/streamable),
     discovers their tools, and registers them as DAWN tools so the agent can
     call them like any built-in tool.
  2. DAWN can expose its own tools via MCP (see _start_dawn_mcp_server).

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
    from mcp.client.streamable_http import StreamableHTTPTransport
    HAS_HTTP_TRANSPORT = True
except ImportError:
    HAS_HTTP_TRANSPORT = False


class AuthStreamableHTTPTransport(StreamableHTTPTransport):
    """StreamableHTTPTransport that injects a bearer token on every request.

    The stock transport has no constructor arg for auth headers, so a
    token-protected HTTP MCP server (e.g. one gated behind an API key) would
    otherwise be unreachable. This subclass adds an `Authorization` header to
    every outbound request by overriding `_prepare_headers`.
    """

    def __init__(self, url: str, bearer_token: str):
        super().__init__(url)
        self._bearer_token = bearer_token

    def _prepare_headers(self) -> dict[str, str]:
        headers = super()._prepare_headers()
        headers["Authorization"] = f"Bearer {self._bearer_token}"
        return headers


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

    # ── Public dispatch ────────────────────────────────────────────────────

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

    # ── Server registry ────────────────────────────────────────────────────

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
            return ToolResult(success=False, error=f"Failed to connect to '{server.get('name')}': {e}")

        self._sessions[server_id] = client

        # Discover and register tools, then persist them.
        try:
            tools = await self._discover_tools(server_id, client)
        except Exception as e:
            await self._disconnect_server(server_id)
            return ToolResult(success=False, error=f"Connected but failed to discover tools: {e}")
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
        api_key = server.get("api_key")
        if api_key and HAS_HTTP_TRANSPORT:
            # Token-protected server — inject the bearer token on every request.
            return Client(AuthStreamableHTTPTransport(url, api_key))
        return Client(url)

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
        """Upsert discovered tools into mcp_tools and register them as DAWN tools."""
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
        # Register each as a DAWN tool so the agent can call it directly.
        registry = get_registry()
        for t in tools:
            if registry.get(f"mcp_{t['name']}") is None:
                registry.register(RemoteMCPTool(server_id, t["name"], t["description"], t["input_schema"]))

    async def _disconnect_server(self, server_id: Optional[str]) -> ToolResult:
        client = self._sessions.pop(server_id, None)
        if client:
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        return ToolResult(success=True, output={"status": "disconnected"})

    # ── Tools / resources ───────────────────────────────────────────────────

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

    # ── Expose DAWN's own tools via MCP ─────────────────────────────────────

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


async def load_persisted_mcp_tools() -> int:
    """Load previously-discovered MCP tools from the DB into the registry.

    Called at startup so tools from connected MCP servers survive a restart —
    otherwise the agent would only see them for the lifetime of the process
    that connected. Returns the number of tools loaded.
    """
    try:
        import db.client as db
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("mcp_tools").select(
            "server_id, name, description, input_schema"
        ).eq("enabled", True).execute())
    except Exception as e:
        logger.warning(f"Failed to load persisted MCP tools: {e}")
        return 0

    registry = get_registry()
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
        logger.info(f"Loaded {count} persisted MCP tool(s) into the registry")
    return count


class RemoteMCPTool(BaseTool):
    """A tool discovered from an external MCP server, registered into DAWN's
    registry so the agent can call it directly (name: 'mcp_<tool_name>')."""

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
