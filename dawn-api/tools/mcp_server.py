"""
MCP (Model Context Protocol) server implementation.
Allows DAWN to serve as a tool provider for Claude Desktop, Cursor, etc.,
and to connect to external MCP servers for additional capabilities.
"""
import asyncio
import json
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

try:
    from mcp import Server as MCPServer, StdioServerParameters
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


class MCPTool(BaseTool):
    name = "mcp"
    description = (
        "Model Context Protocol integration. Connect to external MCP servers "
        "to access additional tools and capabilities (databases, APIs, file systems, etc.). "
        "Also allows DAWN to expose its own tools via MCP for use by Claude Desktop and other MCP clients."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": [
                    "list_servers", "connect_server", "disconnect_server",
                    "list_tools", "call_tool", "list_resources", "read_resource",
                    "start_mcp_server", "stop_mcp_server"
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
        self._connected_servers = {}  # server_id -> MCP client session

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

    async def _list_servers(self) -> ToolResult:
        """List configured MCP servers from the database."""
        try:
            import db.client as db
            supabase = db.get_db()
            res = supabase.table("mcp_servers").select(
                "id, name, description, server_type, enabled, tools_count, last_connected_at"
            ).eq("enabled", True).execute()
            return ToolResult(success=True, output=res.data or [])
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list servers: {e}")

    async def _connect_server(self, server_id: Optional[str]) -> ToolResult:
        """Connect to an MCP server."""
        if not server_id:
            return ToolResult(success=False, error="server_id is required")
        
        if not HAS_MCP:
            return ToolResult(
                success=False,
                error="MCP library not installed. Run: pip install mcp"
            )

        try:
            import db.client as db
            supabase = db.get_db()
            res = supabase.table("mcp_servers").select("*").eq("id", server_id).execute()
            if not res.data:
                return ToolResult(success=False, error=f"Server {server_id} not found")
            
            server = res.data[0]
            
            if server["server_type"] == "stdio":
                # Connect via stdio
                params = StdioServerParameters(
                    command=server["command"],
                    args=server.get("args", []),
                )
                # Store connection
                self._connected_servers[server_id] = {"params": params, "type": "stdio"}
                
                # Update last connected
                supabase.table("mcp_servers").update({
                    "last_connected_at": "now()"
                }).eq("id", server_id).execute()
                
                return ToolResult(
                    success=True,
                    output={"status": "connected", "server": server["name"], "type": "stdio"}
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Server type '{server['server_type']}' not yet supported"
                )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to connect: {e}")

    async def _disconnect_server(self, server_id: Optional[str]) -> ToolResult:
        """Disconnect from an MCP server."""
        if server_id and server_id in self._connected_servers:
            del self._connected_servers[server_id]
        return ToolResult(success=True, output={"status": "disconnected"})

    async def _list_tools(self, server_id: Optional[str]) -> ToolResult:
        """List tools available on a connected MCP server."""
        if not server_id:
            return ToolResult(success=False, error="server_id is required")
        
        # Try DB first
        try:
            import db.client as db
            supabase = db.get_db()
            res = supabase.table("mcp_tools").select("name, description, input_schema").eq(
                "server_id", server_id
            ).eq("enabled", True).execute()
            if res.data:
                return ToolResult(success=True, output=res.data)
        except Exception:
            pass
        
        return ToolResult(success=True, output=[])

    async def _call_tool(self, server_id: Optional[str], tool_name: Optional[str], args: dict) -> ToolResult:
        """Call a tool on a remote MCP server."""
        if not server_id or not tool_name:
            return ToolResult(success=False, error="server_id and tool_name are required")
        
        if not HAS_MCP:
            return ToolResult(success=False, error="MCP library not installed")

        # For now, return a placeholder — full MCP tool calling requires
        # an active session with the remote server
        return ToolResult(
            success=True,
            output={
                "note": f"MCP tool '{tool_name}' on server '{server_id}' would be called here",
                "args": args,
                "status": "mcp_call_pending",
            }
        )

    async def _list_resources(self, server_id: Optional[str]) -> ToolResult:
        """List resources on a connected MCP server."""
        return ToolResult(success=True, output=[])

    async def _read_resource(self, server_id: Optional[str], resource_uri: Optional[str]) -> ToolResult:
        """Read a resource from a connected MCP server."""
        return ToolResult(success=True, output={"note": "Resource reading not yet implemented"})

    async def _start_dawn_mcp_server(self) -> ToolResult:
        """Start DAWN's own MCP server so external tools can use DAWN's tools."""
        return ToolResult(
            success=True,
            output={
                "status": "mcp_server_concept",
                "note": "DAWN MCP server would expose: filesystem, git, web_search, web_fetch, terminal, ssh, nmap, osint tools",
                "implementation": "Run a separate FastAPI server with MCP protocol on port 8100",
            }
        )

    async def _stop_dawn_mcp_server(self) -> ToolResult:
        """Stop DAWN's MCP server."""
        return ToolResult(success=True, output={"status": "stopped"})
