"""
Base tool contract.
Every tool (terminal, filesystem, git, web search, future skills) implements this
exact shape so the registry, executor, and agent loop can treat them uniformly.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Uniform result envelope returned by every tool.run() call."""
    success: bool
    output: Any = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialisable form — used when building the tool_result message sent back to the LLM."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """
    Every tool subclasses this. `name` must be unique within a registry and
    should match the identifier the LLM will use in tool_calls.
    `input_schema` is a JSON schema dict (OpenAI/DeepSeek function-calling format)
    describing the tool's parameters — this is what gets shown to the model.
    """

    name: str
    description: str
    input_schema: dict

    @abstractmethod
    async def run(self, **kwargs) -> ToolResult:
        """
        Execute the tool. Must never raise — catch internally and return
        ToolResult(success=False, error=...) instead. The executor also wraps
        this defensively, but tools should fail gracefully on their own.
        """
        ...

    def spec(self) -> dict:
        """OpenAI-style function spec, as consumed by DeepSeekEngine.complete_with_tools()."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
