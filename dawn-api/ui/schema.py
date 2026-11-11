"""
UI document schema + server-side normalization for `render_component`.

The model emits a host-owned block document (title + a flat list of
top-level blocks). The frontend maps each `type` to a React component it
controls — the model never ships code. This module validates and normalizes
that document, compensating for a weaker design model:

  - every fix is silent but counted in `normalized`,
  - a block with an unknown `type` is *dropped* (counted) rather than
    failing the whole document,
  - limits (block count, nesting depth, rows, document size) are enforced
    here, server-side.

`chart` blocks are enriched with a server-built Vega-Lite spec so the frontend
only ever renders (it never builds specs from raw model data into code).
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Limits (intelligent-ui spec section 4.1) ────────────────────────────────
MAX_TOP_LEVEL_BLOCKS = 40
MAX_NESTING_DEPTH = 2
MAX_TABLE_ROWS = 200
MAX_CHART_ROWS = 500   # matches tools/chart.py
MAX_DOC_BYTES = 200_000

# Aliases applied during normalization (spec 4.5): values are lowercased first.
TONE_ALIASES = {"warning": "warn", "error": "danger"}
CHART_TYPE_ALIASES = {"pie": "arc", "donut": "arc", "scatter": "point"}
NAVIGATE_PREFIXES = ("/approvals", "/canvas", "/artifacts", "/nodes", "/decisions", "/agent-tasks")

VALID_CHART_TYPES = {"bar", "line", "area", "point", "arc"}


# ── Action ──────────────────────────────────────────────────────────────────
class Action(BaseModel):
    kind: Literal["prompt", "navigate", "tool"]
    text: Optional[str] = None
    to: Optional[str] = None
    tool: Optional[str] = None
    args: dict = Field(default_factory=dict)
    inputs: List[str] = Field(default_factory=list)


# ── Blocks ──────────────────────────────────────────────────────────────────
class BaseBlock(BaseModel):
    id: Optional[str] = None


class TextBlock(BaseBlock):
    type: Literal["text"]
    markdown: str = ""


class CalloutBlock(BaseBlock):
    type: Literal["callout"]
    tone: Literal["info", "warn", "danger", "success"] = "info"
    title: Optional[str] = None
    text: str = ""


class StatBlock(BaseBlock):
    type: Literal["stat"]
    label: str
    value: Union[str, float, int]
    unit: Optional[str] = None
    delta: Optional[dict] = None
    hint: Optional[str] = None


class TableBlock(BaseBlock):
    type: Literal["table"]
    columns: Optional[List[dict]] = None
    rows: List[dict] = Field(default_factory=list)
    sortable: bool = False
    caption: Optional[str] = None


class ChartBlock(BaseBlock):
    type: Literal["chart"]
    chart_type: str = "bar"
    data: List[dict] = Field(default_factory=list)
    x_field: str
    y_field: str
    color_field: Optional[str] = None
    title: Optional[str] = None
    # server-enriched:
    vega_spec: Optional[dict] = None


class KeyValueBlock(BaseBlock):
    type: Literal["key_value"]
    items: List[dict] = Field(default_factory=list)


class CodeBlock(BaseBlock):
    type: Literal["code"]
    language: Optional[str] = None
    text: str = ""


class TimelineItem(BaseModel):
    time: str
    title: str
    detail: Optional[str] = None
    status: Optional[Literal["done", "active", "pending", "failed"]] = None


class TimelineBlock(BaseBlock):
    type: Literal["timeline"]
    items: List[TimelineItem] = Field(default_factory=list)


class ButtonBlock(BaseBlock):
    type: Literal["button"]
    label: str
    variant: Literal["primary", "default"] = "default"
    action: Action


class CalcInput(BaseModel):
    id: str
    label: str
    kind: Literal["number", "slider", "text", "select", "toggle"] = "number"
    default: Optional[Any] = None
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    unit: Optional[str] = None
    options: Optional[List[str]] = None


class CalcOutput(BaseModel):
    label: str
    expr: str
    format: Optional[str] = None


class CalcBlock(BaseBlock):
    type: Literal["calc"]
    inputs: List[CalcInput] = Field(default_factory=list)
    outputs: List[CalcOutput] = Field(default_factory=list)
    note: Optional[str] = None


class FormField(BaseModel):
    id: str
    label: str
    kind: Literal["text", "number", "select", "toggle"] = "text"
    default: Optional[Any] = None
    options: Optional[List[str]] = None
    required: bool = False


class FormBlock(BaseBlock):
    type: Literal["form"]
    fields: List[FormField] = Field(default_factory=list)
    submit: dict = Field(default_factory=dict)  # {label, action}


class ApprovalBlock(BaseBlock):
    type: Literal["approval"]
    pending_action_id: Optional[str] = None


class EmbedBlock(BaseBlock):
    type: Literal["embed"]
    code: str = ""
    title: Optional[str] = None


# ── Learning blocks (learning spec §5) ──────────────────────────────────────
class MathBlock(BaseBlock):
    type: Literal["math"]
    tex: str = ""
    display: bool = True
    caption: Optional[str] = None


class PlotSeries(BaseModel):
    expr: str
    label: Optional[str] = None


class PlotBlock(BaseBlock):
    type: Literal["plot"]
    title: Optional[str] = None
    var: str = "x"
    x: Optional[dict] = None
    y: Optional[dict] = None
    params: List[dict] = Field(default_factory=list)   # sliders
    series: List[PlotSeries] = Field(default_factory=list)
    points: List[dict] = Field(default_factory=list)


class StepsItem(BaseModel):
    title: str
    text: Optional[str] = None
    hint: Optional[str] = None
    math: Optional[str] = None


class StepsBlock(BaseBlock):
    type: Literal["steps"]
    title: Optional[str] = None
    reveal: Literal["click", "all"] = "click"
    steps: List[StepsItem] = Field(default_factory=list)


class QuizQuestion(BaseModel):
    id: str
    kind: Literal["mcq", "short"] = "mcq"
    prompt: str
    options: List[str] = Field(default_factory=list)
    answer: Optional[Any] = None
    explanation: Optional[str] = None
    hint: Optional[str] = None


class QuizBlock(BaseBlock):
    type: Literal["quiz"]
    topic_id: Optional[str] = None
    questions: List[QuizQuestion] = Field(default_factory=list)


class CardItem(BaseModel):
    front: str
    back: str


class CardsBlock(BaseBlock):
    type: Literal["cards"]
    topic_id: Optional[str] = None
    items: List[CardItem] = Field(default_factory=list)


class SourcesBlock(BaseBlock):
    type: Literal["sources"]
    items: List[dict] = Field(default_factory=list)  # {n,title,url,publisher,kind,node_id}


class ArgumentObjection(BaseModel):
    text: str
    replies: List[str] = Field(default_factory=list)


class ArgumentBlock(BaseBlock):
    type: Literal["argument"]
    title: Optional[str] = None
    premises: List[dict] = Field(default_factory=list)
    conclusion: Optional[dict] = None
    inference: str = "deductive"
    assessment: Optional[dict] = None
    objections: List[ArgumentObjection] = Field(default_factory=list)


class GraphBlock(BaseBlock):
    type: Literal["graph"]
    direction: str = "LR"
    nodes: List[dict] = Field(default_factory=list)
    edges: List[dict] = Field(default_factory=list)


class DiagramBlock(BaseBlock):
    type: Literal["diagram"]
    kind: str
    controls: List[dict] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


LeafBlock = Union[
    TextBlock, CalloutBlock, StatBlock, TableBlock, ChartBlock,
    KeyValueBlock, CodeBlock, TimelineBlock, ButtonBlock,
    CalcBlock, FormBlock, ApprovalBlock, EmbedBlock,
    MathBlock, PlotBlock, StepsBlock, QuizBlock, CardsBlock,
    SourcesBlock, ArgumentBlock, GraphBlock, DiagramBlock,
]


class ColumnsBlock(BaseBlock):
    type: Literal["columns"]
    children: List[LeafBlock] = Field(min_length=2, max_length=3)


class TabsItem(BaseModel):
    label: str
    children: List[LeafBlock]


class TabsBlock(BaseBlock):
    type: Literal["tabs"]
    tabs: List[TabsItem] = Field(min_length=1, max_length=6)


# `columns`/`tabs` are the only containers; nesting is deliberately capped at
# depth 2 (containers hold leaf blocks only).
Block = Union[LeafBlock, ColumnsBlock, TabsBlock]


class UIDoc(BaseModel):
    v: int = 1
    title: str = ""
    blocks: List[Block] = Field(default_factory=list)


# ── Normalization ───────────────────────────────────────────────────────────
def _norm_value(v: Any) -> Any:
    """Lowercase strings and apply known aliases."""
    if isinstance(v, str):
        return v.strip().lower()
    return v


def _numeric(value: Any) -> Union[float, int, str, None]:
    """Convert a numeric-looking string to a number; otherwise return None."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        s = value.strip()
        try:
            if _re_fullmatch_int(s):
                return int(s)
            f = float(s)
            return int(f) if f.is_integer() else f
        except ValueError:
            return None
    return None


def _re_fullmatch_int(s: str) -> bool:
    if not s:
        return False
    t = s.lstrip("+-")
    return t.isdigit()


def normalize_block(raw: dict, depth: int = 0, id_prefix: str = "b") -> tuple[dict | None, list[str]]:
    """
    Normalize a single raw block. Returns (block_dict | None, errors[]).
    `None` means the block was dropped (unknown type).
    """
    if not isinstance(raw, dict) or "type" not in raw:
        return None, ["block missing 'type'"]

    dtype = _norm_value(raw.get("type"))
    if dtype not in _KNOWN_TYPES:
        return None, [f"unknown block type '{raw.get('type')}'"]
    if depth == 0 and dtype in _CONTAINER_TYPES:
        pass  # containers are valid top-level blocks
    elif dtype in _CONTAINER_TYPES:
        # containers cannot nest inside containers (depth cap)
        return None, [f"block type '{dtype}' cannot be nested"]

    block = dict(raw)

    # Normalize enum-ish string fields.
    if dtype == "callout" and isinstance(block.get("tone"), str):
        t = _norm_value(block["tone"])
        block["tone"] = TONE_ALIASES.get(t, t)
    if dtype == "button" and isinstance(block.get("variant"), str):
        block["variant"] = _norm_value(block["variant"])
        if block["variant"] not in ("primary", "default"):
            block["variant"] = "default"
    if dtype == "chart":
        ct = block.get("chart_type")
        if not isinstance(ct, str):
            return None, ["chart missing chart_type"]
        ct = _norm_value(ct)
        ct = CHART_TYPE_ALIASES.get(ct, ct)
        if ct not in VALID_CHART_TYPES:
            return None, [f"unknown chart_type '{ct}'"]
        block["chart_type"] = ct

    # Assign an id when missing.
    if not block.get("id"):
        block["id"] = id_prefix

    # table.columns inference + row cap + numeric coercion
    if dtype == "table":
        rows = block.get("rows") or []
        if len(rows) > MAX_TABLE_ROWS:
            rows = rows[:MAX_TABLE_ROWS]
            block["rows"] = rows
        if not block.get("columns") and rows:
            block["columns"] = [{"key": str(k), "label": str(k)} for k in rows[0].keys()]
        for row in rows:
            for k, v in list(row.items()):
                num = _numeric(v)
                if num is not None:
                    row[k] = num
        block["rows"] = rows

    if dtype == "chart":
        data = block.get("data") or []
        if len(data) > MAX_CHART_ROWS:
            data = data[:MAX_CHART_ROWS]
        for row in data:
            for k, v in list(row.items()):
                num = _numeric(v)
                if num is not None:
                    row[k] = num
        block["data"] = data
        # Server-build the Vega-Lite spec (never accept raw Vega-Lite).
        from tools.chart import build_vega_spec
        try:
            block["vega_spec"] = build_vega_spec(
                chart_type=block["chart_type"],
                data=data,
                x_field=block.get("x_field", ""),
                y_field=block.get("y_field", ""),
                color_field=block.get("color_field"),
                title=block.get("title") or "",
            )
        except Exception as e:
            return None, [f"chart vega spec failed: {e}"]

    # Recurse into containers (leaf blocks only, depth + 1).
    if dtype == "columns":
        children = []
        errors: list[str] = []
        for i, c in enumerate(list(block.get("children") or [])):
            if depth + 1 > MAX_NESTING_DEPTH:
                errors.append("nesting depth exceeded")
                continue
            nb, errs = normalize_block(c, depth=depth + 1, id_prefix=f"{id_prefix}.{i}")
            if nb is None:
                errors.extend(errs)
            else:
                children.append(nb)
        block["children"] = children[:3]
        if errors:
            return block, errors

    if dtype == "tabs":
        for tab in list(block.get("tabs") or []):
            if not isinstance(tab, dict):
                continue
            children = []
            for i, c in enumerate(list(tab.get("children") or [])):
                nb, errs = normalize_block(c, depth=depth + 1, id_prefix=f"{id_prefix}.{i}")
                if nb is not None:
                    children.append(nb)
            tab["children"] = children
        block["tabs"] = block.get("tabs") or []

    # navigate actions must stay inside the allowlist
    if dtype == "button" and isinstance(block.get("action"), dict):
        act = block["action"]
        if act.get("kind") == "navigate" and isinstance(act.get("to"), str):
            if not act["to"].startswith(NAVIGATE_PREFIXES):
                act["kind"] = "prompt"
                act["text"] = act.get("text") or f"Open {act['to']}"
                del act["to"]

    return block, []


_KNOWN_TYPES = {
    "text", "callout", "stat", "table", "chart", "key_value", "code",
    "timeline", "button", "calc", "form", "approval", "embed",
    "math", "plot", "steps", "quiz", "cards", "sources", "argument",
    "graph", "diagram",
    "columns", "tabs",
}
_CONTAINER_TYPES = {"columns", "tabs"}


def normalize_document(raw: Any) -> dict:
    """
    Normalize a raw render_component payload into a validated UIDoc dict with
    metadata. The result is what gets persisted as a 'ui' artifact `spec`.

    Returns: {v, title, blocks, _meta: {blocks, normalized, dropped}}
    """
    doc: dict = {"v": 1}
    if not isinstance(raw, dict):
        raw = {}
    if isinstance(raw.get("title"), str):
        doc["title"] = raw["title"]
    else:
        doc["title"] = ""

    raw_blocks = raw.get("blocks")
    if not isinstance(raw_blocks, list):
        raw_blocks = []

    # Hard document-size cap (spec 4.1) — a document body over 200 KB is an
    # error, not a silent truncation.
    try:
        body = json.dumps(raw or {}).encode("utf-8")
        if len(body) > MAX_DOC_BYTES:
            return {
                "v": 1, "title": doc["title"], "blocks": [],
                "_meta": {"error": "document exceeds 200 KB limit", "blocks": 0, "normalized": 0, "dropped": len(raw_blocks)},
            }
    except Exception:
        pass

    normalized: list[dict] = []
    dropped: int = 0
    dropped_reasons: list[str] = []

    for i, raw_block in list(enumerate(raw_blocks))[:MAX_TOP_LEVEL_BLOCKS]:
        nb, errs = normalize_block(raw_block, depth=0, id_prefix=f"b{i + 1}")
        if nb is None:
            dropped += 1
            dropped_reasons.extend(errs)
        else:
            normalized.append(nb)

    dropped += len(raw_blocks) - min(len(raw_blocks), MAX_TOP_LEVEL_BLOCKS)
    if dropped and dropped_reasons:
        logger.info("render_component dropped %d block(s): %s", dropped, dropped_reasons[:10])

    doc["blocks"] = normalized
    doc["_meta"] = {
        "blocks": len(normalized),
        "normalized": len(normalized),
        "dropped": dropped,
        "unverified_sources": 0,
    }
    return doc
