"""
Tool registry. Mirrors the get_db() / get_engine() singleton pattern used
elsewhere in dawn-api (see db/client.py, llm/engine.py).
"""
from typing import Optional
import logging
from tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered — overwriting")
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def specs(self) -> list[dict]:
        """OpenAI-style function specs for all registered tools — fed to engine.complete_with_tools()."""
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())


# Singleton
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """Wire up the built-in tools."""
    try:
        from tools.filesystem import FilesystemTool
        registry.register(FilesystemTool())
    except Exception as e:
        logger.error(f"Failed to register FilesystemTool: {e}")

    try:
        from tools.git import GitTool
        registry.register(GitTool())
    except Exception as e:
        logger.error(f"Failed to register GitTool: {e}")

    try:
        from tools.websearch import WebSearchTool
        registry.register(WebSearchTool())
    except Exception as e:
        logger.error(f"Failed to register WebSearchTool: {e}")

    try:
        from skills.installer import SkillInstallTool
        registry.register(SkillInstallTool())
    except Exception as e:
        logger.error(f"Failed to register SkillInstallTool: {e}")

    try:
        from tools.webfetch import WebFetchTool
        registry.register(WebFetchTool())
    except Exception as e:
        logger.error(f"Failed to register WebFetchTool: {e}")
    
    try:
        from tools.terminal import TerminalTool
        registry.register(TerminalTool())
    except Exception as e:
        logger.error(f"Failed to register TerminalTool: {e}")

    # v3.0 — SSH
    try:
        from tools.ssh import SSHTool
        registry.register(SSHTool())
    except Exception as e:
        logger.error(f"Failed to register SSHTool: {e}")

    # v4.0 — MCP
    try:
        from tools.mcp_server import MCPTool
        registry.register(MCPTool())
    except Exception as e:
        logger.error(f"Failed to register MCPTool: {e}")

    # v5.0 — OSINT
    try:
        from tools.osint_tool import OSINTTool
        registry.register(OSINTTool())
    except Exception as e:
        logger.error(f"Failed to register OSINTTool: {e}")

    # v6.0 — Nmap
    try:
        from tools.nmap_tool import NmapTool
        registry.register(NmapTool())
    except Exception as e:
        logger.error(f"Failed to register NmapTool: {e}")

    # v7.0 — Database (full Supabase table access, OWNER tier only —
    # see TIER_TOOL_ACCESS in llm/identity.py)
    try:
        from tools.database import DatabaseTool
        registry.register(DatabaseTool())
    except Exception as e:
        logger.error(f"Failed to register DatabaseTool: {e}")

    # v7.1 — Knowledge graph (read-only context/memory retrieval for Agent
    # mode — gives it what Chat mode already gets automatically, on demand)
    try:
        from tools.knowledge_graph import KnowledgeGraphTool
        registry.register(KnowledgeGraphTool())
    except Exception as e:
        logger.error(f"Failed to register KnowledgeGraphTool: {e}")