"""
autopilot_report — structured finish for autopilot runs.

The job wrapper prompt says: nothing needing attention means call
autopilot_report with status "quiet". run_agent_loop treats this tool as a
final step (stop_on_tools) and the autopilot engine reads the output to build
the run's summary and findings.
"""
from typing import Any
import logging
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

VALID_STATUS = ("quiet", "findings", "blocked")
VALID_SEVERITY = ("info", "warning", "critical")
MAX_ITEMS = 50


class AutopilotReportTool(BaseTool):
    name = "autopilot_report"
    risk = "internal_write"
    is_mutating = False
    description = (
        "End this autonomous run with a structured report. status is 'quiet' when "
        "nothing needs attention, 'findings' when there is something worth reporting, "
        "'blocked' when a decision or approval is needed. Provide a one-line summary "
        "and, for findings/blocked, up to 50 items with title, detail, severity "
        "(info|warning|critical) and an optional ref."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": list(VALID_STATUS)},
            "summary": {"type": "string", "description": "One-line summary of the outcome."},
            "items": {
                "type": "array",
                "description": "Findings/items, each: {title, detail, severity, ref?}.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "severity": {"type": "string", "enum": list(VALID_SEVERITY)},
                        "ref": {"type": "string"},
                    },
                    "required": ["title"],
                },
            },
        },
        "required": ["status", "summary"],
    }

    async def run(self, status: str, summary: str, items: list[dict] | None = None, **kwargs: Any) -> ToolResult:
        if status not in VALID_STATUS:
            return ToolResult(success=False, error=f"status must be one of {','.join(VALID_STATUS)}")
        clean = []
        for it in (items or [])[:MAX_ITEMS]:
            if not isinstance(it, dict) or not it.get("title"):
                continue
            severity = it.get("severity") or "info"
            if severity not in VALID_SEVERITY:
                severity = "info"
            clean.append({
                "title": str(it["title"])[:500],
                "detail": str(it.get("detail") or "")[:2000],
                "severity": severity,
                "ref": str(it["ref"])[:200] if it.get("ref") else None,
            })
        return ToolResult(success=True, output={
            "status": status,
            "summary": str(summary)[:2000],
            "items": clean,
            "unstructured": False,
        })
