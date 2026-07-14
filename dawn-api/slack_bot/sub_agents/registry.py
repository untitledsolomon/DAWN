"""
Sub-Agent Registry — loads YAML definitions and provides lookup/specs.

Architecture:
  SubAgentRegistry (singleton)
    ├── load_all()          → scans sub_agents/ directory for *.yaml
    ├── get(name)           → returns SubAgentDef by name
    ├── list_agents()       → returns all registered sub-agent definitions
    ├── delegate_specs()    → returns tool specs for the supervisor's delegate tools
    └── agent_descriptions() → returns formatted descriptions for system prompt

Each SubAgentDef specifies:
  - name: unique identifier
  - description: what this agent does (shown to supervisor LLM)
  - tools: list of tool names this agent may use
  - system_prompt: the agent's persona/instructions
  - model: which model to route to (optional, defaults to deepseek-chat)
"""

import os
import yaml
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SUB_AGENTS_DIR = os.path.join(os.path.dirname(__file__))


@dataclass
class SubAgentDef:
    """Definition of a sub-agent loaded from a YAML file."""
    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    system_prompt: str = ""
    model: str = "deepseek-chat"


class SubAgentRegistry:
    """Singleton registry of sub-agent definitions."""

    def __init__(self):
        self._agents: dict[str, SubAgentDef] = {}

    def load_all(self) -> int:
        """Scan sub_agents/ directory and load all *.yaml files.
        
        Returns the number of agents loaded.
        """
        count = 0
        if not os.path.isdir(SUB_AGENTS_DIR):
            logger.warning(f"Sub-agents directory not found: {SUB_AGENTS_DIR}")
            return 0

        for filename in sorted(os.listdir(SUB_AGENTS_DIR)):
            if not filename.endswith((".yaml", ".yml")):
                continue
            filepath = os.path.join(SUB_AGENTS_DIR, filename)
            try:
                with open(filepath, "r") as f:
                    data = yaml.safe_load(f)
                if not data or "name" not in data:
                    logger.warning(f"Skipping {filename}: no 'name' field")
                    continue
                agent = SubAgentDef(
                    name=data["name"],
                    description=data.get("description", ""),
                    tools=data.get("tools", []),
                    system_prompt=data.get("system_prompt", ""),
                    model=data.get("model", "deepseek-chat"),
                )
                self._agents[agent.name] = agent
                count += 1
                logger.info(f"Loaded sub-agent: {agent.name} ({len(agent.tools)} tools)")
            except Exception as e:
                logger.error(f"Failed to load sub-agent {filename}: {e}")

        logger.info(f"Loaded {count} sub-agents from {SUB_AGENTS_DIR}")
        return count

    def get(self, name: str) -> Optional[SubAgentDef]:
        """Get a sub-agent definition by name."""
        return self._agents.get(name)

    def list_agents(self) -> list[SubAgentDef]:
        """Return all registered sub-agent definitions."""
        return list(self._agents.values())

    def names(self) -> list[str]:
        """Return all registered sub-agent names."""
        return list(self._agents.keys())

    def delegate_specs(self) -> list[dict]:
        """Return tool specs for the supervisor's delegate tools.
        
        These are injected into the supervisor's tool list so the LLM
        knows which sub-agents are available and what each does.
        """
        specs = []
        for agent in self._agents.values():
            specs.append({
                "type": "function",
                "function": {
                    "name": f"delegate_to_{agent.name}",
                    "description": agent.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": f"The task to delegate to the {agent.name}. Be specific about what you need done."
                            }
                        },
                        "required": ["task"]
                    }
                }
            })
        return specs

    def agent_descriptions(self) -> str:
        """Return formatted descriptions for injection into the supervisor's system prompt."""
        if not self._agents:
            return ""
        lines = ["\n\n## Available Sub-Agents (delegation targets)"]
        lines.append("You have specialist sub-agents you can delegate work to. When a task falls clearly")
        lines.append("into one of these domains, use the corresponding delegate_to_<name> tool rather than")
        lines.append("doing it yourself. This keeps your context focused and lets specialists handle details.")
        lines.append("")
        for agent in self._agents.values():
            tools_str = ", ".join(agent.tools) if agent.tools else "general knowledge"
            lines.append(f"- **{agent.name}**: {agent.description}")
            lines.append(f"  Tools: {tools_str}")
            lines.append("")
        return "\n".join(lines)


# ── Singleton ──────────────────────────────────────────────────────────────

_registry: Optional[SubAgentRegistry] = None


def get_sub_agent_registry() -> SubAgentRegistry:
    """Get or create the singleton SubAgentRegistry."""
    global _registry
    if _registry is None:
        _registry = SubAgentRegistry()
        _registry.load_all()
    return _registry


def reload_sub_agents() -> int:
    """Force-reload all sub-agent definitions. Returns count loaded."""
    global _registry
    _registry = SubAgentRegistry()
    return _registry.load_all()
