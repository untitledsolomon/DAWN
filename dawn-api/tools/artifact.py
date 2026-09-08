"""
General artifact tool — lets the agent push non-chart content onto the Canvas.

Mirrors the create_chart / create_explainer pattern: it builds a validated
artifact payload and hands it back; persistence (inserting into the `artifacts`
table) and the `artifact` SSE event are handled by routers/agent.py, which has
the session_id this tool doesn't know about.

Supports:
  - table: a structured table rendered from `spec` (data rows).
  - note:  a free-form text/note card (renders from `code` as plain text).
  - file:  a reference to an external file/URL (`url`).
"""
from typing import Any, Optional
import logging
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_ROWS = 1000
VALID_TYPES = {"table", "note", "file"}


class CreateArtifactTool(BaseTool):
    name = "create_artifact"
    description = (
        "Push a non-chart item onto DAWN's Canvas workspace. Use this when the "
        "user asks you to save, add, or pin a table, a written note/summary, or a "
        "reference to a file — something that isn't best shown as a chart (for "
        "charts use create_chart, for animated explainers use create_explainer). "
        "The item appears on the Canvas page for the user to review."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the artifact, shown on the Canvas card.",
            },
            "artifact_type": {
                "type": "string",
                "enum": sorted(VALID_TYPES),
                "description": (
                    "table: structured data shown as a table. note: a written "
                    "summary/note shown as text. file: a reference to a file/URL."
                ),
            },
            "description": {
                "type": "string",
                "description": "Optional 1-2 sentence summary shown under the title.",
            },
            "data": {
                "type": "array",
                "description": (
                    "For 'table': rows of data as flat objects, e.g. "
                    f"[{{\"name\": \"Axis\", \"count\": 12}}, ...]. Max {MAX_ROWS} rows."
                ),
                "items": {"type": "object"},
            },
            "content": {
                "type": "string",
                "description": "For 'note': the text of the note/summary.",
            },
            "url": {
                "type": "string",
                "description": "For 'file': the URL or path of the file to reference.",
            },
        },
        "required": ["title", "artifact_type"],
    }

    async def run(
        self,
        title: str,
        artifact_type: str,
        description: Optional[str] = None,
        data: Optional[list[dict[str, Any]]] = None,
        content: Optional[str] = None,
        url: Optional[str] = None,
    ) -> ToolResult:
        if artifact_type not in VALID_TYPES:
            return ToolResult(
                success=False,
                error=f"Invalid artifact_type '{artifact_type}'. Must be one of: {', '.join(sorted(VALID_TYPES))}.",
            )

        if artifact_type == "table":
            if not isinstance(data, list) or not data:
                return ToolResult(success=False, error="'data' must be a non-empty list of row objects for a table.")
            if not all(isinstance(row, dict) for row in data):
                return ToolResult(success=False, error="Every item in 'data' must be an object/row, not a scalar.")
            if len(data) > MAX_ROWS:
                logger.info(f"[CreateArtifactTool] Truncating {len(data)} rows to {MAX_ROWS}")
                data = data[:MAX_ROWS]
            return ToolResult(
                success=True,
                output={
                    "title": title,
                    "description": description,
                    "spec": {"data": data},
                    "row_count": len(data),
                },
                metadata={"artifact_type": "table"},
            )

        if artifact_type == "note":
            if not content or not str(content).strip():
                return ToolResult(success=False, error="'content' is required for a note artifact.")
            return ToolResult(
                success=True,
                output={
                    "title": title,
                    "description": description,
                    "code": str(content),
                },
                metadata={"artifact_type": "note"},
            )

        # file
        if not url or not str(url).strip():
            return ToolResult(success=False, error="'url' is required for a file artifact.")
        return ToolResult(
            success=True,
            output={
                "title": title,
                "description": description,
                "url": str(url),
            },
            metadata={"artifact_type": "file"},
        )
