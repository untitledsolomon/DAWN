"""Decision Workflow Tool — registered in DAWN's agent tool registry.

This is the primary entry point for the LLM to invoke decision workflows.
The LLM's job is limited to:
  1. Parsing the human's ambiguous request into a structured workflow invocation
  2. Narrating the already-computed results (never inventing numbers)
  3. Flagging anomalies the structured engine wouldn't catch
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
                "description": "Name of the workflow (e.g., 'reroute_shipment')"
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
            }
        },
        "required": ["workflow_name"]
    }

    async def run(self, **kwargs) -> ToolResult:
        try:
            result = run_workflow(
                kwargs.get("workflow_name", ""),
                kwargs.get("inputs", {})
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