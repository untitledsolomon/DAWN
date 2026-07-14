"""
Delegate Tools — allow the supervisor agent to hand off work to sub-agents.

Two tools:
  1. delegate_to_subagent(name, task) — single handoff to one specialist
  2. delegate_parallel(delegations) — run multiple sub-agents concurrently

These tools are registered in the supervisor's tool list alongside all
other tools. The supervisor decides when to delegate based on the task.
"""

import json
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult
from slack_bot.sub_agents.runner import run_sub_agent, run_parallel_sub_agents
from slack_bot.sub_agents.registry import get_sub_agent_registry

logger = logging.getLogger(__name__)


def _normalize_delegations(delegations) -> list[dict]:
    """Normalize delegations from various LLM output formats into list of dicts.

    The LLM sometimes sends delegations as:
      - list of dicts: [{"agent_name": "...", "task": "..."}]
      - list of tuples: [("ops_agent", "check health")]
      - list of lists: [["ops_agent", "check health"]]
      - tuple of tuples: (("ops_agent", "check health"),)
    """
    if not delegations:
        return []

    # If it's a tuple, convert to list
    if isinstance(delegations, tuple):
        delegations = list(delegations)

    if not isinstance(delegations, list):
        return []

    normalized = []
    for d in delegations:
        if isinstance(d, dict):
            # Already a dict — use as-is
            normalized.append(d)
        elif isinstance(d, (list, tuple)) and len(d) >= 2:
            # [name, task] or (name, task) format
            normalized.append({
                "agent_name": str(d[0]),
                "task": str(d[1]),
                "context": d[2] if len(d) > 2 else None,
            })
        else:
            logger.warning(f"Skipping malformed delegation item: {d}")
    return normalized


class DelegateToSubAgentTool(BaseTool):
    """Delegate a task to a specialist sub-agent.

    The supervisor calls this when a task falls clearly into one of the
    sub-agent domains (CRM, ops, research, code, comms, data, axis, forge, security).
    The sub-agent runs in its own isolated context with restricted tools.
    """

    name = "delegate_to_subagent"
    description = (
        "Delegate a task to a specialist sub-agent. Use this when a task clearly "
        "falls into a specific domain (CRM, operations, research, code, communications, "
        "data analysis, Axis ERP, Forge CMS, or security). The sub-agent has its own "
        "tools and context. Available sub-agents: crm_agent, ops_agent, research_agent, "
        "code_agent, comms_agent, data_agent, axis_agent, forge_agent, security_agent."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the sub-agent to delegate to. One of: crm_agent, ops_agent, research_agent, code_agent, comms_agent, data_agent, axis_agent, forge_agent, security_agent.",
                "enum": [
                    "crm_agent", "ops_agent", "research_agent", "code_agent",
                    "comms_agent", "data_agent", "axis_agent", "forge_agent", "security_agent"
                ],
            },
            "task": {
                "type": "string",
                "description": "The task to delegate. Be specific about what you need done and what information to look for.",
            },
        },
        "required": ["agent_name", "task"],
    }

    async def run(self, **kwargs) -> ToolResult:
        agent_name = kwargs.get("agent_name", "")
        task = kwargs.get("task", "")

        if not agent_name or not task:
            return ToolResult(
                success=False,
                error="Both 'agent_name' and 'task' are required.",
            )

        # Verify the sub-agent exists
        registry = get_sub_agent_registry()
        agent_def = registry.get(agent_name)
        if not agent_def:
            available = ", ".join(registry.names())
            return ToolResult(
                success=False,
                error=f"Unknown sub-agent '{agent_name}'. Available: {available}",
            )

        logger.info(f"Delegating to sub-agent '{agent_name}': {task[:100]}...")

        result = await run_sub_agent(
            agent_name=agent_name,
            task=task,
        )

        if result["success"]:
            return ToolResult(
                success=True,
                output={
                    "agent": agent_name,
                    "result": result["result"],
                    "iterations": result["iterations"],
                },
                metadata={"agent": agent_name, "iterations": result["iterations"]},
            )
        else:
            return ToolResult(
                success=False,
                error=result.get("error", "Sub-agent returned no result"),
                metadata={"agent": agent_name, "iterations": result["iterations"]},
            )


class DelegateParallelTool(BaseTool):
    """Delegate multiple tasks to multiple sub-agents in parallel.

    Use this when a complex task can be split into independent parts that
    different specialists can work on simultaneously. For example, researching
    a competitor while also checking internal CRM data.
    """

    name = "delegate_parallel"
    description = (
        "Delegate multiple tasks to multiple sub-agents in parallel. Use this when "
        "a complex task can be split into independent parts that different specialists "
        "can work on simultaneously. Each delegation specifies an agent_name and task. "
        "Available sub-agents: crm_agent, ops_agent, research_agent, code_agent, "
        "comms_agent, data_agent, axis_agent, forge_agent, security_agent."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "delegations": {
                "type": "array",
                "description": "List of delegations to run in parallel. Each must have agent_name and task.",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the sub-agent.",
                            "enum": [
                                "crm_agent", "ops_agent", "research_agent", "code_agent",
                                "comms_agent", "data_agent", "axis_agent", "forge_agent", "security_agent"
                            ],
                        },
                        "task": {
                            "type": "string",
                            "description": "The task for this sub-agent.",
                        },
                    },
                    "required": ["agent_name", "task"],
                },
                "minItems": 1,
                "maxItems": 5,
            },
        },
        "required": ["delegations"],
    }

    async def run(self, **kwargs) -> ToolResult:
        raw_delegations = kwargs.get("delegations", [])

        # Normalize: LLM sometimes sends tuples/lists instead of dicts
        delegations = _normalize_delegations(raw_delegations)

        if not delegations:
            return ToolResult(
                success=False,
                error="At least one delegation is required. Pass delegations as a list of {agent_name, task} objects.",
            )

        # Validate all agent names
        registry = get_sub_agent_registry()
        for d in delegations:
            agent_name = d.get("agent_name", "")
            if not registry.get(agent_name):
                return ToolResult(
                    success=False,
                    error=f"Unknown sub-agent '{agent_name}'. Available: {', '.join(registry.names())}",
                )

        logger.info(f"Running {len(delegations)} sub-agents in parallel: {[d.get('agent_name', '?') for d in delegations]}")

        results = await run_parallel_sub_agents(delegations)

        # Format results
        output_lines = []
        all_success = True
        for agent_name, result in results.items():
            if result["success"]:
                output_lines.append(f"[{agent_name}] SUCCESS ({result['iterations']} iterations):")
                output_lines.append(result["result"][:500])
            else:
                all_success = False
                output_lines.append(f"[{agent_name}] FAILED: {result.get('error', 'Unknown error')}")

        return ToolResult(
            success=all_success,
            output="\n\n".join(output_lines),
            metadata={"agents": list(results.keys()), "count": len(results)},
        )
