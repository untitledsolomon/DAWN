"""
Tests for the Intelligent UI document schema and server-side normalization.

Run with `pytest -q` in dawn-api. The module needs pydantic (a FastAPI dep).
"""
import json

import pytest

from ui.schema import (
    MAX_TOP_LEVEL_BLOCKS,
    MAX_TABLE_ROWS,
    MAX_CHART_ROWS,
    normalize_document,
)


def _doc(blocks, title="UI document"):
    return {"title": title, "blocks": blocks}


def test_minimal_text_block():
    d = normalize_document(_doc([{"type": "text", "markdown": "hi"}]))
    assert d["_meta"]["blocks"] == 1
    assert d["_meta"]["dropped"] == 0
    assert d["blocks"][0]["type"] == "text"
    assert d["blocks"][0]["id"].startswith("b")


def test_unknown_block_type_is_dropped_not_fatal():
    d = normalize_document(_doc([
        {"type": "text", "markdown": "kept"},
        {"type": "not_a_real_block", "x": 1},
    ]))
    assert d["_meta"]["blocks"] == 1
    assert d["_meta"]["dropped"] == 1
    assert d["blocks"][0]["markdown"] == "kept"


def test_numeric_strings_coerced_in_chart_and_table():
    d = normalize_document(_doc([{
        "type": "chart", "chart_type": "bar", "x_field": "cat", "y_field": "n",
        "data": [{"cat": "a", "n": "12"}, {"cat": "b", "n": "4.5"}],
    }]))
    chart = d["blocks"][0]
    assert chart["data"][0]["n"] == 12
    assert chart["data"][1]["n"] == 4.5
    # the server builds the Vega-Lite spec — raw Vega-Lite is never accepted
    assert chart["vega_spec"]["encoding"]["y"]["field"] == "n"

    d2 = normalize_document(_doc([{
        "type": "table", "rows": [{"a": "3", "b": "x"}, {"a": "7", "b": "y"}],
    }]))
    table = d2["blocks"][0]
    assert table["rows"][0]["a"] == 3
    # columns inferred from the first row
    assert table["columns"][0]["key"] == "a"


def test_chart_type_aliases():
    d = normalize_document(_doc([{
        "type": "chart", "chart_type": "pie", "x_field": "cat", "y_field": "n",
        "data": [{"cat": "a", "n": 1}],
    }]))
    assert d["blocks"][0]["chart_type"] == "arc"


def test_tone_aliases():
    d = normalize_document(_doc([{"type": "callout", "tone": "error", "text": "x"}]))
    assert d["blocks"][0]["tone"] == "danger"


def test_navigate_action_allowlist():
    good = normalize_document(_doc([{
        "type": "button", "label": "Go", "action": {"kind": "navigate", "to": "/approvals"},
    }]))
    assert good["blocks"][0]["action"]["kind"] == "navigate"

    bad = normalize_document(_doc([{
        "type": "button", "label": "Go", "action": {"kind": "navigate", "to": "https://evil.example"},
    }]))
    assert bad["blocks"][0]["action"]["kind"] == "prompt"  # downgraded, not a link


def test_top_level_block_limit():
    blocks = [{"type": "text", "markdown": f"b{i}"} for i in range(MAX_TOP_LEVEL_BLOCKS + 5)]
    d = normalize_document(_doc(blocks))
    assert len(d["blocks"]) == MAX_TOP_LEVEL_BLOCKS
    assert d["_meta"]["dropped"] == 5


def test_table_rows_truncated():
    rows = [{"i": k} for k in range(MAX_TABLE_ROWS + 10)]
    d = normalize_document(_doc([{"type": "table", "rows": rows}]))
    assert len(d["blocks"][0]["rows"]) == MAX_TABLE_ROWS


def test_chart_data_truncated():
    data = [{"c": "x", "n": i} for i in range(MAX_CHART_ROWS + 10)]
    d = normalize_document(_doc([{
        "type": "chart", "chart_type": "line", "x_field": "c", "y_field": "n", "data": data,
    }]))
    assert len(d["blocks"][0]["data"]) == MAX_CHART_ROWS


def test_document_size_cap():
    big = {"type": "text", "markdown": "x" * 400_000}
    d = normalize_document(_doc([big]))
    # over 200 KB the whole document errors rather than rendering a partial doc
    assert d["_meta"].get("error")


def test_unknown_extra_props_dropped():
    d = normalize_document(_doc([{
        "type": "text", "markdown": "ok", "onclick": "alert(1)", "data_url": "x",
    }]))
    block = d["blocks"][0]
    assert "onclick" not in block
    assert "data_url" not in block


def test_columns_nesting_caps_at_two_levels():
    d = normalize_document(_doc([{
        "type": "columns",
        "children": [{"type": "stat", "label": "a", "value": 1}],
    }]))
    assert len(d["blocks"][0]["children"]) == 1

    deep = normalize_document(_doc([{
        "type": "columns",
        "children": [{"type": "columns", "children": [{"type": "text", "markdown": "x"}]}],
    }]))
    assert deep["blocks"][0]["children"] == []
