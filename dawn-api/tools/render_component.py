"""
render_component — the Intelligent UI tool.

The model emits a host-owned document: a title plus a flat list of blocks. The
frontend maps each block `type` to a React component it controls, so the model
never ships code. This tool validates and normalizes the document server-side
(see dawn-api/ui/schema.py), rejects documents over the size limits, and hands
the normalized doc back for persistence as a 'ui' artifact.

The tool itself does not persist — routers/agent.py does that, exactly like
create_chart.
"""
import logging
from typing import Any
from tools.base import BaseTool, ToolResult
from ui.schema import normalize_document, MAX_TOP_LEVEL_BLOCKS

logger = logging.getLogger(__name__)


class RenderComponentTool(BaseTool):
    name = "render_component"
    risk = "internal_write"
    is_mutating = False
    description = (
        "Build an interface (a UI document) when the answer is better shown than "
        "told. Use it when the answer has at least one of: 2+ items compared across "
        "2+ attributes; numbers over time or across categories; a what-if the user "
        "will tweak; a choice that needs input; an action needing approval; 4+ "
        "status items. Put 'title' first. 'blocks' is a list of blocks rendered in "
        "order as they are written; each block has a 'type' plus its props. "
        "Max 40 top-level blocks, nesting (columns/tabs) max 2 levels deep, table "
        "max 200 rows, chart data max 500 rows, whole document max 200 KB. Use "
        "'stat' for headline numbers, 'columns' of stats for a KPI row, 'table' or "
        "'chart' for comparisons, 'callout' for warnings, 'timeline' for event "
        "lists, 'text' for short prose. Otherwise answer in prose without calling "
        "this tool. Gather the data first (knowledge_graph / web) and never invent "
        "numbers to fill a block."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Short title for the interface. Put this first.",
            },
            "blocks": {
                "type": "array",
                "description": (
                    f"The blocks to render, in authoring order (max {MAX_TOP_LEVEL_BLOCKS}). "
                    "Block types: text, callout, stat, table, chart, key_value, code, "
                    "timeline, columns, tabs, button, calc, form, approval, embed."
                ),
                "items": {"type": "object"},
            },
        },
        "required": ["title", "blocks"],
    }

    async def run(self, title: str, blocks: list[dict], **kwargs: Any) -> ToolResult:
        if blocks is None:
            blocks = []
        if not isinstance(blocks, list):
            return ToolResult(
                success=False,
                error="'blocks' must be a list of block objects.",
            )

        doc = normalize_document({"title": title or "", "blocks": blocks})

        meta = doc.get("_meta") or {}
        if meta.get("error"):
            return ToolResult(success=False, error=meta["error"])

        if meta.get("blocks", 0) == 0:
            return ToolResult(
                success=False,
                error=(
                    "render_component: no valid blocks survived normalization "
                    f"({meta.get('dropped', 0)} dropped: unknown or malformed type). "
                    "Re-emit the document with valid block types."
                ),
            )

        summary_meta = {
            "blocks": meta.get("blocks", 0),
            "normalized": meta.get("normalized", 0),
            "dropped": meta.get("dropped", 0),
        }
        return ToolResult(
            success=True,
            output={
                "title": doc.get("title", ""),
                "doc": doc,
                "metadata": summary_meta,
                "description": f"UI document — {summary_meta['blocks']} block(s)",
            },
            metadata={"artifact_type": "ui"},
        )
