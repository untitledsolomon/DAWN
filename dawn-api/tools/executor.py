"""
Tool executor. Takes a tool_call (name + args) as emitted by the LLM,
validates it against the registry, runs it, and guarantees a ToolResult
comes back no matter what — the agent loop should never have to handle
a raw exception from a tool.

Write-gating: native tools marked `is_mutating` (or whose name matches the
mutating prefix convention) are queued for human approval via the
pending_actions queue instead of executing immediately.
"""
import logging
from tools.base import ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


async def _execute_native(tool_name: str, args: dict) -> ToolResult:
    """Execute an approved native-tool action (registered as the native
    executor for the pending_actions queue)."""
    from tools.registry import get_registry
    return await execute_tool_call(get_registry(), tool_name, args)


def _register_native_executor() -> None:
    from tools import pending_actions
    pending_actions.register_native_executor(_execute_native)


async def execute_tool_call(registry: ToolRegistry, name: str, args: dict) -> ToolResult:
    tool = registry.get(name)

    if tool is None:
        logger.warning(f"Unknown tool requested by LLM: '{name}'")
        return ToolResult(
            success=False,
            error=f"Unknown tool '{name}'. Available tools: {', '.join(registry.names())}",
        )

    # Write-gating for native mutating tools: queue for approval instead of
    # executing. MCP tools are gated inside tools/mcp_server.py; this covers
    # every native tool (current and future) automatically.
    from tools.pending_actions import is_mutating_tool, queue_pending_action
    if getattr(tool, "is_mutating", False) or is_mutating_tool(name):
        return await queue_pending_action(None, name, args)

    try:
        result = await tool.run(**args)
        if not isinstance(result, ToolResult):
            # Defensive — a misbehaving tool returned a raw value instead of ToolResult
            logger.warning(f"Tool '{name}' returned non-ToolResult ({type(result)}) — wrapping")
            return ToolResult(success=True, output=result)
        return result
    except TypeError as e:
        # Usually a bad/missing kwarg — surface it clearly so the LLM can retry with corrected args
        logger.warning(f"Tool '{name}' called with bad args {args}: {e}")
        return ToolResult(success=False, error=f"Invalid arguments for '{name}': {e}")
    except Exception as e:
        logger.exception(f"Tool '{name}' raised during execution")
        return ToolResult(success=False, error=f"Tool '{name}' failed: {e}")
