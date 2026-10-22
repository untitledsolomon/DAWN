"""
Runtime setting definitions. Every tunable in DAWN is declared here once
(type, range, default, label, description, group). The database stores only
overrides; the Settings UI is rendered from the registry metadata, so a new
tunable is one registry entry and no frontend work.

Defaults equal today's behaviour (this rollout changes nothing by itself);
autopilot keys are new. `env` names a Settings() attribute that supplies the
pre-DB value. `hot=False` means the value needs a restart to apply.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: Literal["int", "float", "bool", "str", "enum", "list[str]", "nullable_float"]
    default: Any
    label: str
    description: str
    group: str               # settings tab / section
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple[str, ...] = ()
    unit: str | None = None
    env: str | None = None   # Settings attribute supplying the pre-DB value
    hot: bool = True         # False => "applies after restart" chip
    advanced: bool = False


def _d(**kw) -> SettingDef:
    return SettingDef(**kw)


SETTING_DEFS: dict[str, SettingDef] = {
    # ── Agent loop ────────────────────────────────────────────────────────
    "agent.max_iterations": _d(
        key="agent.max_iterations", type="int", default=100, min=1, max=500,
        label="Max iterations", description="Upper bound on agent loop steps per turn.",
        group="Agent and limits",
    ),
    "agent.repeat_threshold": _d(
        key="agent.repeat_threshold", type="int", default=3, min=2, max=10,
        label="Repeat threshold",
        description="Stop when the same tool call repeats identically this many times.",
        group="Agent and limits",
    ),
    "agent.history_turns": _d(
        key="agent.history_turns", type="int", default=10, min=0, max=50,
        label="History turns",
        description="How many prior turns of conversation history reach the model.",
        group="Agent and limits",
    ),

    # ── LLM engine ────────────────────────────────────────────────────────
    "llm.mode": _d(
        key="llm.mode", type="enum", default="deepseek", choices=("deepseek", "local"),
        env="llm_mode", label="LLM mode",
        description="Inference backend: DeepSeek API or a local llama.cpp model.",
        group="Model",
    ),
    "llm.model": _d(
        key="llm.model", type="str", default="deepseek-chat", env="deepseek_model",
        label="Model", description="Model name used for completions.", group="Model",
    ),
    "llm.tool_max_tokens": _d(
        key="llm.tool_max_tokens", type="int", default=8192, min=512, max=32768,
        label="Tool call max tokens", description="Max tokens for a tool-calling completion.",
        group="Model",
    ),
    "llm.tool_temperature": _d(
        key="llm.tool_temperature", type="float", default=0.1, min=0.0, max=1.5, step=0.05,
        label="Tool call temperature", description="Sampling temperature for tool turns.",
        group="Model",
    ),
    "llm.chat_max_tokens": _d(
        key="llm.chat_max_tokens", type="int", default=2048, min=128, max=16384,
        label="Chat max tokens", description="Max tokens for plain chat completions.",
        group="Model",
    ),
    "llm.chat_temperature": _d(
        key="llm.chat_temperature", type="float", default=0.7, min=0.0, max=1.5, step=0.05,
        label="Chat temperature", description="Sampling temperature for plain chat.",
        group="Model",
    ),
    "llm.price_input_per_mtok": _d(
        key="llm.price_input_per_mtok", type="nullable_float", default=None, min=0.0,
        label="Input price ($ / 1M tokens)", description="Leave empty to show tokens only.",
        group="Model",
    ),
    "llm.price_output_per_mtok": _d(
        key="llm.price_output_per_mtok", type="nullable_float", default=None, min=0.0,
        label="Output price ($ / 1M tokens)", description="Leave empty to show tokens only.",
        group="Model",
    ),
    "llm.price_cached_input_per_mtok": _d(
        key="llm.price_cached_input_per_mtok", type="nullable_float", default=None, min=0.0,
        label="Cached input price ($ / 1M tokens)",
        description="Leave empty to show tokens only.", group="Model",
    ),

    # ── Tools ─────────────────────────────────────────────────────────────
    "tools.disabled": _d(
        key="tools.disabled", type="list[str]", default=[], label="Disabled tools",
        description="Tool names hidden from the model entirely (e.g. ['terminal']).",
        group="Tools",
    ),
    "tools.terminal_timeout_default": _d(
        key="tools.terminal_timeout_default", type="int", default=30, min=5, max=300,
        label="Terminal timeout (default)", description="Default seconds before a terminal command times out.",
        group="Tools", unit="s",
    ),
    "tools.terminal_timeout_max": _d(
        key="tools.terminal_timeout_max", type="int", default=120, min=30, max=900,
        label="Terminal timeout (max)", description="Hard cap on terminal command time.", group="Tools", unit="s",
    ),
    "tools.web_timeout": _d(
        key="tools.web_timeout", type="int", default=10, min=2, max=60,
        label="Web timeout", description="Seconds before a web search/fetch times out.",
        group="Tools", unit="s",
    ),
    "tools.chart_max_rows": _d(
        key="tools.chart_max_rows", type="int", default=500, min=10, max=5000,
        label="Chart max rows", description="Rows a chart accepts before truncating.",
        group="Tools",
    ),
    "tools.artifact_max_rows": _d(
        key="tools.artifact_max_rows", type="int", default=1000, min=10, max=10000,
        label="Artifact max rows", description="Rows a table artifact accepts before truncating.",
        group="Tools",
    ),

    # ── Sub-agents ────────────────────────────────────────────────────────
    "subagent.max_iterations": _d(
        key="subagent.max_iterations", type="int", default=30, min=1, max=200,
        label="Sub-agent max iterations",
        description="Iteration cap for a delegated sub-agent.", group="Agent and limits",
    ),

    # ── Memory ────────────────────────────────────────────────────────────
    "memory.extract_mode": _d(
        key="memory.extract_mode", type="enum", default="always",
        choices=("always", "conditional", "off"), label="Memory extraction",
        description="'conditional' skips extraction for short exchanges with no tool calls.",
        group="Agent and limits",
    ),

    # ── App / UI ──────────────────────────────────────────────────────────
    "app.timezone": _d(
        key="app.timezone", type="str", default="Africa/Kampala",
        label="Timezone", description="IANA name; used by schedules and daily rollover.",
        group="General",
    ),
    "ui.density": _d(
        key="ui.density", type="enum", default="auto", choices=("auto", "off"),
        label="UI density", description="'off' disables generated interfaces.",
        group="General",
    ),

    # ── Autopilot ─────────────────────────────────────────────────────────
    "autopilot.enabled": _d(
        key="autopilot.enabled", type="bool", default=False,
        label="Autopilot enabled", description="Master switch — nothing autonomous runs while off.",
        group="Autopilot defaults", advanced=True,
    ),
    "autopilot.poll_seconds": _d(
        key="autopilot.poll_seconds", type="int", default=30, min=5, max=300,
        label="Poll seconds", description="How often the scheduler checks for due jobs.",
        group="Autopilot defaults", unit="s",
    ),
    "autopilot.max_concurrent_runs": _d(
        key="autopilot.max_concurrent_runs", type="int", default=1, min=1, max=5,
        label="Max concurrent runs", description="Global cap on simultaneous job runs.",
        group="Autopilot defaults",
    ),
    "autopilot.default_max_steps": _d(
        key="autopilot.default_max_steps", type="int", default=25, min=1, max=200,
        label="Default max steps", description="Per-run runaway cap on agent steps.",
        group="Autopilot defaults",
    ),
    "autopilot.default_max_tokens": _d(
        key="autopilot.default_max_tokens", type="int", default=500000, min=10000, max=5000000,
        label="Default max tokens", description="Per-run runaway cap on tokens.",
        group="Autopilot defaults",
    ),
    "autopilot.default_max_seconds": _d(
        key="autopilot.default_max_seconds", type="int", default=600, min=30, max=3600,
        label="Default max seconds", description="Per-run wall-clock cap.", group="Autopilot defaults", unit="s",
    ),
    "autopilot.min_interval_minutes": _d(
        key="autopilot.min_interval_minutes", type="int", default=5, min=1, max=1440,
        label="Min interval (minutes)", description="Hard floor against schedules firing far too often.",
        group="Autopilot defaults", unit="min",
    ),
    "autopilot.event_coalesce_seconds": _d(
        key="autopilot.event_coalesce_seconds", type="int", default=120, min=0, max=3600,
        label="Event coalesce (seconds)", description="Same-type events inside this window merge into one run.",
        group="Autopilot defaults", unit="s",
    ),
    "autopilot.max_event_runs_per_hour": _d(
        key="autopilot.max_event_runs_per_hour", type="int", default=4, min=1, max=60,
        label="Max event runs / hour", description="Per-job ceiling on event-triggered runs.",
        group="Autopilot defaults",
    ),
    "autopilot.retry_max_attempts": _d(
        key="autopilot.retry_max_attempts", type="int", default=2, min=0, max=5,
        label="Retry max attempts", description="Transient-failure retries per step.",
        group="Autopilot defaults",
    ),
    "autopilot.max_consecutive_failures": _d(
        key="autopilot.max_consecutive_failures", type="int", default=3, min=1, max=20,
        label="Max consecutive failures", description="Auto-pause a job after this many failed runs.",
        group="Autopilot defaults",
    ),
    "autopilot.cost_alert_daily": _d(
        key="autopilot.cost_alert_daily", type="nullable_float", default=None, min=0.0,
        label="Daily cost alert ($)", description="Soft alert only — jobs keep running.",
        group="Autopilot defaults",
    ),
    "autopilot.cost_hard_cap_daily": _d(
        key="autopilot.cost_hard_cap_daily", type="nullable_float", default=None, min=0.0,
        label="Daily hard cap ($)", description="When set, jobs stop for the day at the cap.",
        group="Autopilot defaults", advanced=True,
    ),
    "autopilot.run_retention_days": _d(
        key="autopilot.run_retention_days", type="int", default=90, min=7, max=730,
        label="Run retention (days)", description="How long run history is kept before pruning.",
        group="Autopilot defaults", unit="d",
    ),
}


def setting_defs() -> list[SettingDef]:
    return list(SETTING_DEFS.values())
