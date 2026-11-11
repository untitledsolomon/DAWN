"""
BlockStreamer — splits a streaming render_component tool-call payload into
individual top-level blocks as soon as each one is complete.

The model streams the arguments of a `render_component` call as arbitrary
fragments. Each fragment may cut a string or JSON value at any point. This
class is a small, string- and escape-aware incremental scanner: it finds
`"blocks"`, enters the array, and returns each top-level object the moment its
closing `}` arrives. It never json-parses the whole document, so a partial
tail is harmless.

Correctness depends on the scanner being resumable at any byte offset
(arbitrary chunk boundaries) — feed() carries all state between calls.
"""
from __future__ import annotations

import json


class BlockStreamer:
    def __init__(self) -> None:
        self._buf = ""
        self._i = 0                 # next char index to process
        self._mode = "seek"         # seek | between | object | end
        self._in_string = False
        self._esc = False
        self._string_val = ""       # the string token currently being read
        self._blocks_seen = False   # saw the top-level "blocks" key
        self._depth = 0             # object brace depth while in 'object'
        self._obj_start = -1

    @property
    def finished(self) -> bool:
        return self._mode == "end"

    def feed(self, chunk: str) -> list[dict]:
        """Feed one arguments fragment; return the raw blocks completed so far."""
        if self._mode == "end":
            return []
        self._buf += chunk
        out: list[dict] = []
        n = len(self._buf)
        i = self._i
        while i < n:
            c = self._buf[i]

            # Inside a block object: only strings matter (ignore {} inside them).
            if self._mode == "object":
                if self._in_string:
                    if self._esc:
                        self._esc = False
                    elif c == "\\":
                        self._esc = True
                    elif c == '"':
                        self._in_string = False
                    i += 1
                    continue
                if c == '"':
                    self._in_string = True
                elif c == "{":
                    self._depth += 1
                elif c == "}":
                    self._depth -= 1
                    if self._depth == 0:
                        raw = self._buf[self._obj_start : i + 1]
                        try:
                            parsed = json.loads(raw)
                            if isinstance(parsed, dict):
                                out.append(parsed)
                        except (ValueError, TypeError):
                            pass  # malformed block — normalize_document drops it later
                        self._mode = "between"
                i += 1
                continue

            # Inside a string at the top level (doc prologue or between elements).
            if self._in_string:
                if self._esc:
                    self._esc = False
                elif c == "\\":
                    self._esc = True
                elif c == '"':
                    self._in_string = False
                    if self._mode == "seek" and self._string_val == "blocks":
                        self._blocks_seen = True
                    self._string_val = ""
                else:
                    self._string_val += c
                i += 1
                continue

            # Not inside a string.
            if self._mode == "seek":
                if c == '"':
                    self._in_string = True
                    self._string_val = ""
                elif c == "[" and self._blocks_seen:
                    self._mode = "between"
                i += 1
                continue

            if self._mode == "between":
                if c in " \t\r\n,":
                    i += 1
                    continue
                if c == "]":
                    self._mode = "end"
                    i += 1
                    continue
                if c == "{":
                    self._depth = 1
                    self._obj_start = i
                    self._mode = "object"
                    i += 1
                    continue
                if c == '"':
                    self._in_string = True
                i += 1
                continue

            # mode == "end"
            break

        self._i = i
        return out
