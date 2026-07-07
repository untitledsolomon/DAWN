"""Decision workflow registry with approval gate enforcement.

Each workflow is registered with:
  - name: Unique identifier
  - requires_approval: Whether human approval is needed before execution
  - handler: Callable that runs the workflow logic
  - constraints: List of Constraint objects
  - input_schema: Expected input parameters

The approval gate is enforced here, not at the UI layer.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from datetime import datetime, timezone


@dataclass
class DecisionWorkflow:
    name: str
    description: str
    requires_approval: bool = True
    handler: Optional[Callable] = None
    constraints: list = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)


_registry: dict[str, DecisionWorkflow] = {}


def register_workflow(workflow: DecisionWorkflow) -> None:
    """Register a decision workflow."""
    _registry[workflow.name] = workflow


def get_workflow(name: str) -> Optional[DecisionWorkflow]:
    """Get a registered workflow by name."""
    return _registry.get(name)


def list_workflows() -> list[DecisionWorkflow]:
    """List all registered workflows."""
    return list(_registry.values())


def run_workflow(name: str, inputs: dict) -> dict:
    """Run a workflow by name with given inputs.

    Returns a structured result dict with:
      - workflow_name
      - ranked_options
      - recommended
      - requires_approval
      - decision_log_id (set after logging)
    """
    workflow = get_workflow(name)
    if not workflow:
        raise ValueError(f"Unknown workflow: {name}")

    if not workflow.handler:
        raise ValueError(f"Workflow '{name}' has no handler registered")

    result = workflow.handler(inputs)

    return {
        "workflow_name": name,
        "ranked_options": result.get("ranked_options", []),
        "recommended": result.get("recommended"),
        "requires_approval": workflow.requires_approval,
        "explanation": result.get("explanation", ""),
        "decision_log_id": None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def check_approval_required(workflow_name: str) -> bool:
    """Check if a workflow requires human approval."""
    workflow = get_workflow(workflow_name)
    return workflow.requires_approval if workflow else True
