"""
Tool executor. Takes a tool_call (name + args) as emitted by the LLM,
validates it against the registry, runs it, and guarantees a ToolResult
comes back no matter what — the agent loop should never have to handle
a raw exception from a tool.
"""
import logging
from tools.base import ToolResult
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


async def execute_tool_call(registry: ToolRegistry, name: str, args: dict) -> ToolResult:
    tool = registry.get(name)

    if tool is None:
        logger.warning(f"Unknown tool requested by LLM: '{name}'")
        return ToolResult(
            success=False,
            error=f"Unknown tool '{name}'. Available tools: {', '.join(registry.names())}",
        )

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
