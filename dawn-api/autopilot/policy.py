"""
Autopilot run policy and budget — enforced OUTSIDE the model.

RunBudget caps steps, tokens, wall clock and honours cancellation. RunPolicy
implements the Observe/Propose autonomy modes at the tool level: Observe never
exposes `external_write` or `exec` tools; Propose queues them for approval with
provenance. Both live in this leaf module so llm/agent.py can import them
without importing the autopilot package (which imports the agent loop).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

# Risk classes (tools/base.py `risk` attribute, default 'exec' = fail closed).
RISK_READ = "read"
RISK_INTERNAL_WRITE = "internal_write"
RISK_EXTERNAL_WRITE = "external_write"
RISK_EXEC = "exec"


class BudgetExceeded(Exception):
    """Raised by RunBudget before a model call when a cap is hit."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind   # steps | tokens | time | cancelled


@dataclass
class RunBudget:
    max_steps: Optional[int] = None
    max_tokens: Optional[int] = None
    max_seconds: Optional[float] = None
    cancelled: Optional[Callable[[], bool]] = None

    def __post_init__(self) -> None:
        self._start: float = time.monotonic()
        self._steps: int = 0
        self._tokens: int = 0

    def check_step(self) -> None:
        if self.cancelled and self.cancelled():
            raise BudgetExceeded("cancelled", "Run cancelled by user.")
        if self.max_seconds is not None and time.monotonic() - self._start >= self.max_seconds:
            raise BudgetExceeded("time", "Wall-clock limit reached.")
        if self.max_steps is not None and self._steps >= self.max_steps:
            raise BudgetExceeded("steps", f"Step limit reached ({self.max_steps}).")
        self._steps += 1

    def add_tokens(self, tokens: Optional[int]) -> None:
        if not tokens:
            return
        self._tokens += int(tokens)
        if self.max_tokens is not None and self._tokens >= self.max_tokens:
            raise BudgetExceeded("tokens", f"Token limit reached ({self.max_tokens}).")

    @property
    def tokens(self) -> int:
        return self._tokens


@dataclass
class RunPolicy:
    """Observe/Propose autonomy. mode 'unrestricted' = normal chat (no gate)."""
    mode: str = "observe"
    allowlist: set[str] = field(default_factory=set)   # exec tools allowed in propose
    requested_by: Optional[str] = None                 # e.g. autopilot:<job>:<run>

    @property
    def enforced(self) -> bool:
        return self.mode in ("observe", "propose")

    def filters_tool(self, name: str, risk: str) -> Optional[str]:
        """Return a reason string to hide the tool, or None to offer it."""
        if self.mode == "observe":
            if risk in (RISK_EXTERNAL_WRITE, RISK_EXEC):
                return f"{name} is '{risk}' and Observe mode does not expose it"
        elif self.mode == "propose":
            if risk == RISK_EXEC and name not in self.allowlist:
                return f"{name} is 'exec' and not in the tool allowlist"
        return None

    def queues(self, name: str, risk: str) -> bool:
        """Propose mode queues external writes and allowlisted exec tools."""
        if self.mode == "propose":
            if risk == RISK_EXTERNAL_WRITE:
                return True
            if risk == RISK_EXEC and name in self.allowlist:
                return True
        return False
