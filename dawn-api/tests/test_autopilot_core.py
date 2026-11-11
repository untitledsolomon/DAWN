"""Autopilot core policy/budget tests (no database needed)."""

import pytest

from autopilot.policy import BudgetExceeded, RunBudget, RunPolicy


def test_budget_steps_cap():
    budget = RunBudget(max_steps=2)
    budget.check_step()
    budget.check_step()
    with pytest.raises(BudgetExceeded) as exc:
        budget.check_step()
    assert exc.value.kind == "steps"


def test_budget_tokens_cap():
    budget = RunBudget(max_tokens=10)
    budget.check_step()
    budget.add_tokens(4)
    budget.add_tokens(6)  # crosses 10
    with pytest.raises(BudgetExceeded) as exc:
        budget.add_tokens(1)
    assert exc.value.kind == "tokens"


def test_budget_cancelled():
    state = {"cancel": False}
    budget = RunBudget(cancelled=lambda: state["cancel"])
    state["cancel"] = True
    with pytest.raises(BudgetExceeded) as exc:
        budget.check_step()
    assert exc.value.kind == "cancelled"


def test_observe_filters_exec_and_external_write():
    p = RunPolicy(mode="observe")
    assert p.filters_tool("terminal", "exec") is not None
    assert p.filters_tool("send_email", "external_write") is not None
    assert p.filters_tool("knowledge_graph", "read") is None
    assert p.filters_tool("create_chart", "internal_write") is None


def test_propose_filters_non_allowlisted_exec():
    p = RunPolicy(mode="propose", allowlist={"terminal"})
    assert p.filters_tool("nmap", "exec") is not None
    assert p.filters_tool("terminal", "exec") is None
    assert p.filters_tool("web_fetch", "read") is None


def test_propose_queues_external_write_and_allowlisted_exec():
    p = RunPolicy(mode="propose", allowlist={"terminal"}, requested_by="autopilot:j:r")
    assert p.queues("send_email", "external_write") is True
    assert p.queues("terminal", "exec") is True
    assert p.queues("nmap", "exec") is False
    assert p.queues("web_fetch", "read") is False
    assert p.requested_by == "autopilot:j:r"


def test_unrestricted_has_no_gate():
    p = RunPolicy(mode="unrestricted")
    assert not p.enforced
    assert p.queues("send_email", "external_write") is False
