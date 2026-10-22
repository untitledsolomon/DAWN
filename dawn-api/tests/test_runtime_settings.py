"""Tests for runtime settings registry defaults and validation."""
import pytest

from runtime_settings.registry import SETTING_DEFS
from runtime_settings.store import RuntimeSettingsStore


def test_registry_has_expected_keys():
    for key in (
        "agent.max_iterations", "agent.repeat_threshold", "agent.history_turns",
        "llm.tool_max_tokens", "tools.disabled", "memory.extract_mode",
        "app.timezone", "autopilot.enabled", "autopilot.min_interval_minutes",
        "autopilot.cost_hard_cap_daily",
    ):
        assert key in SETTING_DEFS, key


def test_defaults_match_today_s_behaviour():
    s = RuntimeSettingsStore()
    assert s.get("agent.max_iterations") == 100
    assert s.get("agent.repeat_threshold") == 3
    assert s.get("agent.history_turns") == 10
    assert s.get("tools.chart_max_rows") == 500
    assert s.get("tools.artifact_max_rows") == 1000
    assert s.get("autopilot.enabled") is False
    assert s.get("memory.extract_mode") == "always"


def test_validation():
    s = RuntimeSettingsStore()
    # int range
    assert s.validate("agent.max_iterations", 0) is not None
    assert s.validate("agent.max_iterations", 501) is not None
    assert s.validate("agent.max_iterations", 25) is None
    assert s.validate("agent.max_iterations", "x") is not None
    # enum
    assert s.validate("llm.mode", "deepseek") is None
    assert s.validate("llm.mode", "gpt") is not None
    # bool
    assert s.validate("autopilot.enabled", True) is None
    assert s.validate("autopilot.enabled", "yes") is not None
    # list[str]
    assert s.validate("tools.disabled", ["terminal"]) is None
    assert s.validate("tools.disabled", [1, 2]) is not None
    # nullable_float accepts null and >= 0
    assert s.validate("autopilot.cost_hard_cap_daily", None) is None
    assert s.validate("autopilot.cost_hard_cap_daily", 5.0) is None
    assert s.validate("autopilot.cost_hard_cap_daily", -1) is not None
    # unknown key
    assert s.validate("nope", 1) is not None


def test_snapshot_prefix():
    s = RuntimeSettingsStore()
    snap = s.snapshot(prefix="autopilot.")
    assert "autopilot.enabled" in snap
    assert all(k.startswith("autopilot.") for k in snap)
