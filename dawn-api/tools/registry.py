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


# ── Singleton ───────────────────────────────────────────────────────────────────────────

_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry) -> None:
    """
    Wire up the built-in tools. Imported lazily inside this function (rather
    than at module top) so that importing tools.registry never fails just
    because e.g. GitPython isn't installed in some environment — each tool
    module is responsible for its own optional dependencies.
    """
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

    # OMNI geospatial dashboard tool
    try:
        from tools.omni import OmniTool
        registry.register(OmniTool())
    except Exception as e:
        logger.error(f"Failed to register OmniTool: {e}")

    # Chart tool — builds Vega-Lite specs, rendered by dawn-ui's ChartRenderer
    try:
        from tools.chart import ChartTool
        registry.register(ChartTool())
    except Exception as e:
        logger.error(f"Failed to register ChartTool: {e}")

    # OSINT recon tool
    try:
        from tools.osint_tool import OSINTTool
        registry.register(OSINTTool())
    except Exception as e:
        logger.error(f"Failed to register OSINTTool: {e}")

    # v30.0 — Pentesting tool (wraps 35+ security tools)
    try:
        from tools.pentest_tool import PentestTool
        registry.register(PentestTool())
    except Exception as e:
        logger.error(f"Failed to register PentestTool: {e}")

    # v32.0 — Decision Intelligence tools
    try:
        from tools.decision_workflow import DecisionWorkflowTool
        registry.register(DecisionWorkflowTool())
    except Exception as e:
        logger.error(f"Failed to register DecisionWorkflowTool: {e}")

    try:
        from tools.ontology import OntologyQueryTool
        registry.register(OntologyQueryTool())
    except Exception as e:
        logger.error(f"Failed to register OntologyQueryTool: {e}")
