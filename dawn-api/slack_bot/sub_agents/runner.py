"""
Sub-Agent Runner — executes sub-agents in isolated context windows.

Architecture:
  run_sub_agent(name, task, context)
    ├── Looks up SubAgentDef from registry
    ├── Builds isolated message list with sub-agent's system prompt
    ├── Runs agent loop with restricted tool set
    └── Returns only the final result (no intermediate steps)

  run_parallel_sub_agents(delegations)
    ├── Runs multiple sub-agents concurrently via asyncio.gather()
    └── Returns dict of {agent_name: result}

This keeps the supervisor's context clean — it only sees what each
sub-agent decided to return, not every tool call it made along the way.
"""

import json
import logging
from typing import Optional
from llm.engine import get_engine, DeepSeekEngine, DAWN_SYSTEM_PROMPT
from llm.safety import AGENT_SAFETY_PROMPT
from tools.registry import get_registry
from tools.executor import execute_tool_call
from slack_bot.sub_agents.registry import get_sub_agent_registry, SubAgentDef

logger = logging.getLogger(__name__)

MAX_SUB_AGENT_ITERATIONS = 30


async def run_sub_agent(
    agent_name: str,
    task: str,
    context: Optional[dict] = None,
) -> dict:
    """Run a sub-agent with its own isolated context and restricted tools.

    Args:
        agent_name: Name of the sub-agent (must be registered)
        task: The task description to give the sub-agent
        context: Optional context dict (e.g., {"user_message": "...", "history": [...]})

    Returns:
        dict with {"success": bool, "result": str, "error": str|None, "iterations": int}
    """
    registry = get_sub_agent_registry()
    agent_def = registry.get(agent_name)

    if not agent_def:
        return {
            "success": False,
            "result": None,
            "error": f"Unknown sub-agent: '{agent_name}'. Available: {', '.join(registry.names())}",
            "iterations": 0,
        }

    engine = get_engine()
    if not isinstance(engine, DeepSeekEngine):
        return {
            "success": False,
            "result": None,
            "error": "Sub-agents require DeepSeek engine (tool-calling mode)",
            "iterations": 0,
        }

    tool_registry = get_registry()

    # Build isolated message list
    system = (
        agent_def.system_prompt
        + "\n\n"
        + DAWN_SYSTEM_PROMPT
        + "\n\n"
        + AGENT_SAFETY_PROMPT
        + "\n\nYou are running as a sub-agent. You have access to a restricted set of tools. "
        "Complete the task assigned to you and return your final answer. "
        "Do not describe actions you haven't taken — actually use the tools."
    )

    messages = [{"role": "system", "content": system}]

    # Add context if provided
    if context:
        if "history" in context:
            for turn in context["history"][-5:]:
                messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": task})

    # Restrict tools to what this sub-agent is allowed
    allowed_tools = set(agent_def.tools)
    all_tools = tool_registry.list_tools()
    available_specs = [
        t.spec() for t in all_tools
        if t.name in allowed_tools
    ]

    if not available_specs:
        logger.warning(f"Sub-agent '{agent_name}' has no available tools (allowed: {allowed_tools})")

    logger.info(f"Running sub-agent '{agent_name}' with {len(available_specs)} tools")

    iterations = 0
    final_result = None

    for iteration in range(1, MAX_SUB_AGENT_ITERATIONS + 1):
        iterations = iteration
        try:
            result = await engine.complete_with_tools(messages, tools=available_specs)
        except Exception as e:
            logger.exception(f"Sub-agent '{agent_name}' LLM call failed")
            return {
                "success": False,
                "result": final_result,
                "error": f"LLM call failed: {e}",
                "iterations": iterations,
            }

        if result.wants_tool_call:
            # Execute tool calls
            messages.append(engine.assistant_tool_call_message(result.content, result.tool_calls))

            for call in result.tool_calls:
                if call.name not in allowed_tools:
                    logger.warning(f"Sub-agent '{agent_name}' attempted disallowed tool '{call.name}'")
                    error_msg = f"Tool '{call.name}' is not available to this sub-agent"
                    messages.append(engine.tool_result_message(
                        tool_call_id=call.id,
                        tool_name=call.name,
                        result_json=json.dumps({"success": False, "output": None, "error": error_msg, "metadata": {}}),
                    ))
                    continue

                tool_result = await execute_tool_call(tool_registry, call.name, call.args)
                messages.append(engine.tool_result_message(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    result_json=json.dumps(tool_result.to_dict()),
                ))

            continue  # Get another completion

        # No tool call — this is the final answer
        final_result = result.content
        break

    return {
        "success": True,
        "result": final_result or "No output produced.",
        "error": None,
        "iterations": iterations,
    }


async def run_parallel_sub_agents(delegations: list[dict]) -> dict[str, dict]:
    """Run multiple sub-agents in parallel.

    Args:
        delegations: List of dicts, each with {"agent_name": str, "task": str, "context": dict|None}

    Returns:
        dict mapping agent_name to its result dict
    """
    import asyncio

    async def _run_one(d: dict) -> tuple[str, dict]:
        # Use .get() for safety — handles malformed dicts gracefully
        name = d.get("agent_name", "unknown")
        result = await run_sub_agent(
            agent_name=name,
            task=d.get("task", ""),
            context=d.get("context"),
        )
        return name, result

    tasks = [_run_one(d) for d in delegations]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = {}
    for i, result in enumerate(results):
        name = delegations[i].get("agent_name", f"agent_{i}") if i < len(delegations) else f"agent_{i}"
        if isinstance(result, Exception):
            output[name] = {
                "success": False,
                "result": None,
                "error": str(result),
                "iterations": 0,
            }
        else:
            output[name] = result

    return output
