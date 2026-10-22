"""Tests for BlockStreamer — splitting a streaming render_component payload into blocks."""
import json

from ui.stream import BlockStreamer

FIXTURE = json.dumps({
    "title": 'UI "with braces" { and } escaped',
    "blocks": [
        {"type": "stat", "label": "A", "value": 1},
        {"type": "table", "rows": [{"a": 1, "b": "x"}], "columns": [{"key": "a", "label": "A"}]},
        {"type": "callout", "tone": "warn", "text": 'note with "quotes", {braces} and \\n newline'},
    ],
})


def _stream(s: str) -> list[dict]:
    bs = BlockStreamer()
    out: list[dict] = []
    for ch in s:
        out.extend(bs.feed(ch))
    assert bs.finished
    return out


def test_streams_whole_document():
    blocks = _stream(FIXTURE)
    assert [b["type"] for b in blocks] == ["stat", "table", "callout"]


def test_every_byte_offset_is_resumable():
    expected = _stream(FIXTURE)
    for cut in range(1, len(FIXTURE)):
        bs = BlockStreamer()
        got: list[dict] = []
        got.extend(bs.feed(FIXTURE[:cut]))
        got.extend(bs.feed(FIXTURE[cut:]))
        assert got == expected, f"block streamer mismatch at byte offset {cut}"


def test_empty_and_tail_chunks_are_harmless():
    bs = BlockStreamer()
    assert bs.feed("") == []
    blocks = []
    blocks.extend(bs.feed(FIXTURE[:10]))
    blocks.extend(bs.feed(""))
    blocks.extend(bs.feed(FIXTURE[10:]))
    blocks.extend(bs.feed(""))
    assert [b["type"] for b in blocks] == ["stat", "table", "callout"]
