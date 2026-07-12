"""Decision Workflow Tool — registered in DAWN's agent tool registry.

This is the primary entry point for the LLM to invoke decision workflows.
The LLM's job is limited to:
  1. Parsing the human's ambiguous request into a structured workflow invocation
  2. Narrating the already-computed results (never inventing numbers)
  3. Flagging anomalies the structured engine wouldn't catch

Workflows themselves are data (ontology_workflows table), not Python
files — see decision_engine/registry.py. This tool never needs to know
what workflows exist; it just passes the name through.
"""

from tools.base import BaseTool, ToolResult
from decision_engine.registry import run_workflow


class DecisionWorkflowTool(BaseTool):
    name = "decision_workflow_run"
    description = "Run a decision workflow with deterministic constraint checking. Use when the user needs a structured, auditable recommendation."
    input_schema = {
        "type": "object",
        "properties": {
            "workflow_name": {
                "type": "string",
                "description": "Name of the workflow (e.g., 'reroute_shipment'). Call decision_workflow_list first if unsure what's available."
            },
            "inputs": {
                "type": "object",
                "description": "Workflow-specific input parameters",
                "default": {}
            },
            "triggered_by": {
                "type": "string",
                "description": "Who/what triggered this workflow",
                "default": "agent"
            },
            "client_id": {
                "type": "string",
                "description": "Client/tenant scope, if applicable. Omit for the shared/default tenant.",
                "default": None
            }
        },
        "required": ["workflow_name"]
    }

    async def run(self, **kwargs) -> ToolResult:
        try:
            result = await run_workflow(
                kwargs.get("workflow_name", ""),
                kwargs.get("inputs", {}),
                client_id=kwargs.get("client_id"),
            )
            result["triggered_by"] = kwargs.get("triggered_by", "agent")
            return ToolResult(success=True, output=result)
        except ValueError as e:
            return ToolResult(success=False, output={
                "error": str(e),
                "workflow_name": kwargs.get("workflow_name", ""),
                "ranked_options": [],
                "recommended": None,
                "explanation": f"Workflow not found or failed: {str(e)}"
            })
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DecisionWorkflowListTool(BaseTool):
    name = "decision_workflow_list"
    description = "List available decision workflows and what inputs each expects. Call this before decision_workflow_run if you don't already know the workflow's name and input schema."
    input_schema = {
        "type": "object",
        "properties": {
            "client_id": {
                "type": "string",
                "description": "Client/tenant scope, if applicable. Omit for the shared/default tenant.",
                "default": None
            }
        },
        "required": []
    }

    async def run(self, **kwargs) -> ToolResult:
        from decision_engine.registry import list_workflows
        try:
            workflows = await list_workflows(client_id=kwargs.get("client_id"))
            return ToolResult(success=True, output=[
                {
                    "name": wf.name,
                    "description": wf.description,
                    "input_schema": wf.input_schema,
                    "requires_approval": wf.requires_approval,
                }
                for wf in workflows
            ])
        except Exception as e:
            return ToolResult(success=False, error=str(e))
