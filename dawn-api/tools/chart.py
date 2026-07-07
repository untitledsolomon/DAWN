"""
Chart tool — lets the agent turn data into a Vega-Lite chart spec.

This tool does NOT persist anything itself. It just builds and validates a
spec and hands it back as the tool's output. Persistence (inserting into the
`artifacts` table) and notifying the frontend (the `artifact` SSE event) are
handled by the caller (routers/agent.py), which already has the session_id
this tool doesn't know about.

Kept deliberately small: a handful of common Vega-Lite mark types built from
plain (field_name -> value) row dicts, rather than accepting a raw Vega-Lite
spec from the model. Free-form specs from the LLM are a bigger validation
surface (arbitrary "transform"/"data.url" entries, etc.) for very little
benefit — the model doesn't need anything fancier than "chart these rows this way".
"""
from typing import Any, Optional
import logging
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

MAX_ROWS = 500
VALID_CHART_TYPES = {"bar", "line", "area", "point", "arc"}  # arc == pie/donut in Vega-Lite


class ChartTool(BaseTool):
    name = "create_chart"
    description = (
        "Turn tabular data into a chart the user can see. Use this whenever the user "
        "asks you to visualize, chart, graph, or plot something, or when showing a "
        "table/list of numbers as a chart would communicate it better than text. "
        "You provide the rows of data plus which fields to plot; this tool builds a "
        "Vega-Lite chart spec that gets rendered inline for the user. Gather the "
        "underlying data first (e.g. via the knowledge_graph tool) before calling this."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the chart, shown above it.",
            },
            "chart_type": {
                "type": "string",
                "enum": sorted(VALID_CHART_TYPES),
                "description": (
                    "bar: compare categories. line/area: trends over an ordered field "
                    "(e.g. time). point: scatter/correlation. arc: pie/donut, proportion of a whole."
                ),
            },
            "data": {
                "type": "array",
                "description": (
                    f"Rows of data as flat objects, e.g. "
                    f"[{{\"category\": \"Axis\", \"count\": 12}}, ...]. Max {MAX_ROWS} rows — "
                    "aggregate or sample first if you have more."
                ),
                "items": {"type": "object"},
            },
            "x_field": {
                "type": "string",
                "description": "Which field in each row goes on the x-axis (or the category/slice field for 'arc').",
            },
            "y_field": {
                "type": "string",
                "description": "Which field in each row goes on the y-axis (or the value field for 'arc').",
            },
            "color_field": {
                "type": "string",
                "description": "Optional field to color/group by (e.g. a category splitting the data into series).",
            },
            "description": {
                "type": "string",
                "description": "Optional 1-2 sentence summary of what this chart shows — stored alongside it.",
            },
        },
        "required": ["title", "chart_type", "data", "x_field", "y_field"],
    }

    async def run(
        self,
        title: str,
        chart_type: str,
        data: list[dict[str, Any]],
        x_field: str,
        y_field: str,
        color_field: Optional[str] = None,
        description: Optional[str] = None,
    ) -> ToolResult:
        if chart_type not in VALID_CHART_TYPES:
            return ToolResult(
                success=False,
                error=f"Invalid chart_type '{chart_type}'. Must be one of: {', '.join(sorted(VALID_CHART_TYPES))}.",
            )

        if not isinstance(data, list) or not data:
            return ToolResult(success=False, error="'data' must be a non-empty list of row objects.")

        if not all(isinstance(row, dict) for row in data):
            return ToolResult(success=False, error="Every item in 'data' must be an object/row, not a scalar.")

        if len(data) > MAX_ROWS:
            logger.info(f"[ChartTool] Truncating {len(data)} rows to {MAX_ROWS}")
            data = data[:MAX_ROWS]

        missing_x = [i for i, row in enumerate(data) if x_field not in row]
        missing_y = [i for i, row in enumerate(data) if y_field not in row]
        if missing_x:
            return ToolResult(success=False, error=f"x_field '{x_field}' missing from {len(missing_x)} row(s).")
        if missing_y:
            return ToolResult(success=False, error=f"y_field '{y_field}' missing from {len(missing_y)} row(s).")

        def infer_type(field: str) -> str:
            for row in data:
                val = row.get(field)
                if val is None:
                    continue
                if isinstance(val, bool):
                    return "nominal"
                if isinstance(val, (int, float)):
                    return "quantitative"
                return "nominal"
            return "nominal"

        if chart_type == "arc":
            encoding = {
                "theta": {"field": y_field, "type": "quantitative"},
                "color": {"field": x_field, "type": "nominal"},
            }
            mark = {"type": "arc", "innerRadius": 50}
        else:
            encoding = {
                "x": {"field": x_field, "type": infer_type(x_field)},
                "y": {"field": y_field, "type": infer_type(y_field)},
            }
            if color_field:
                encoding["color"] = {"field": color_field, "type": infer_type(color_field)}
            mark = {"type": chart_type, "tooltip": True}

        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "data": {"values": data},
            "mark": mark,
            "encoding": encoding,
            "width": "container",
            "height": 300,
        }

        return ToolResult(
            success=True,
            output={
                "title": title,
                "description": description,
                "spec": spec,
                "row_count": len(data),
            },
            metadata={"artifact_type": "chart"},
        )
