"""
Filesystem tool — sandboxed to FILESYSTEM_SANDBOX_ROOT (config.settings).
All paths given by the LLM are treated as relative to that root and resolved
defensively so that '..' traversal can't escape it. This is the pattern
terminal.py and git.py should also follow for any filesystem-touching op.
"""
from pathlib import Path
import logging
from tools.base import BaseTool, ToolResult
from config import settings
import base64

logger = logging.getLogger(__name__)


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = (
        "Read, write, append, list, delete, view, surgically edit (str_replace / "
        "insert), or check existence of files. Paths are resolved against the "
        "machine (absolute paths used as-is; relative paths resolve against the "
        "current working directory). "
        "For large files (roughly >2000 words / >8000 characters), do NOT attempt one giant "
        "'write' call — it will be truncated by the response token limit. Instead: use 'write' "
        "for the first chunk, then one or more 'append' calls for the rest, writing the content "
        "in sequential pieces of a few thousand characters each. For targeted edits to an "
        "existing file, prefer 'str_replace' (replace an exact substring) or 'insert' (add "
        "content after a specific line) over re-writing the whole file."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "append", "list", "delete", "exists",
                         "view", "str_replace", "insert"],
                "description": "The filesystem operation to perform.",
            },
            "path": {
                "type": "string",
                "description": "Path to the file, e.g. 'projects/foo/notes.md' or an absolute path like 'C:/Users/me/notes.md'.",
            },
            "content": {
                "type": "string",
                "description": (
                    "Content to write, append, or insert. Required for 'write', 'append', and 'insert'. "
                    "For large content, base64-encoding is recommended to avoid JSON escaping issues."
                ),
            },
            "content_encoding": {
                "type": "string",
                "enum": ["utf8", "base64"],
                "description": "How 'content' is encoded. Default 'utf8'. Use 'base64' for content with "
                               "characters that are awkward to escape in JSON.",
            },
            "old_str": {
                "type": "string",
                "description": "For 'str_replace': the exact text to replace. Must match exactly once in the file.",
            },
            "new_str": {
                "type": "string",
                "description": "For 'str_replace': the replacement text.",
            },
            "line_number": {
                "type": "integer",
                "description": "For 'insert': the line number to insert content after (1-indexed).",
            },
            "start_line": {
                "type": "integer",
                "description": "For 'view': optional 1-indexed start line (inclusive).",
            },
            "end_line": {
                "type": "integer",
                "description": "For 'view': optional 1-indexed end line (inclusive).",
            },
            "max_characters": {
                "type": "integer",
                "description": "For 'view': truncate the output to this many characters.",
            },
        },
        "required": ["operation", "path"],
    }

    def __init__(self):
        self.sandbox_enabled = getattr(settings, "filesystem_sandbox_enabled", True)
        root = getattr(settings, "filesystem_sandbox_root", None) or "./sandbox"
        self.root = Path(root).resolve()
        if self.sandbox_enabled:
            self.root.mkdir(parents=True, exist_ok=True)
            logger.info(f"FilesystemTool sandboxed to: {self.root}")
        else:
            logger.info("FilesystemTool sandbox disabled — paths resolved against the machine")

    def _resolve(self, path: str) -> Path:
        if not self.sandbox_enabled:
            # Sandbox disabled: resolve the path as given. Absolute paths are
            # used as-is; relative paths resolve against the current working
            # directory.
            return Path(path).resolve()
        candidate = (self.root / path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"Path '{path}' escapes the sandbox root")
        return candidate

    async def run(
        self,
        operation: str,
        path: str,
        content: str | None = None,
        content_encoding: str = "utf8",
        old_str: str | None = None,
        new_str: str | None = None,
        line_number: int | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        max_characters: int | None = None,
    ) -> ToolResult:
        # Explicit content decoding — never guess. Only decode when the caller
        # explicitly asks for base64, so a valid base64-looking plaintext
        # string is never mis-decoded.
        if content is not None and content_encoding == "base64":
            try:
                content = base64.b64decode(content, validate=True).decode("utf-8")
            except (ValueError, base64.binascii.Error) as e:
                return ToolResult(success=False, error=f"Invalid base64 content: {e}")

        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

        if operation == "read":
            if not target.is_file():
                return ToolResult(success=False, error=f"'{path}' is not a file or does not exist")
            try:
                return ToolResult(success=True, output=target.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                return ToolResult(success=False, error=f"'{path}' is not valid UTF-8 text")

        if operation == "view":
            if not target.is_file():
                return ToolResult(success=False, error=f"'{path}' is not a file or does not exist")
            try:
                lines = target.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                return ToolResult(success=False, error=f"'{path}' is not valid UTF-8 text")
            total = len(lines)
            # Resolve the requested range (1-indexed, inclusive).
            s = start_line or 1
            e = end_line or total
            s = max(1, s)
            e = min(total, e)
            if s > e:
                return ToolResult(success=False, error=f"start_line ({s}) is after end_line ({e})")
            selected = lines[s - 1:e]
            numbered = "\n".join(f"{i + s}\t{ln}" for i, ln in enumerate(selected))
            if max_characters and len(numbered) > max_characters:
                numbered = numbered[:max_characters] + "\n…(truncated)"
            return ToolResult(
                success=True,
                output=numbered,
                metadata={"total_lines": total, "start_line": s, "end_line": e},
            )

        if operation == "str_replace":
            if old_str is None:
                return ToolResult(success=False, error="'old_str' is required for the 'str_replace' operation")
            if not target.is_file():
                return ToolResult(success=False, error=f"'{path}' is not a file or does not exist")
            try:
                text = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return ToolResult(success=False, error=f"'{path}' is not valid UTF-8 text")
            count = text.count(old_str)
            if count == 0:
                return ToolResult(success=False, error=f"'old_str' was not found in '{path}'")
            if count > 1:
                return ToolResult(
                    success=False,
                    error=f"'old_str' appears {count} times in '{path}' — refusing to edit an ambiguous match. "
                          f"Make 'old_str' unique (include more surrounding context).",
                )
            new_text = text.replace(old_str, new_str or "")
            target.write_text(new_text, encoding="utf-8")
            return ToolResult(success=True, output=f"Replaced 1 occurrence in '{path}'.")

        if operation == "insert":
            if content is None:
                return ToolResult(success=False, error="'content' is required for the 'insert' operation")
            if not target.is_file():
                return ToolResult(success=False, error=f"'{path}' is not a file or does not exist")
            try:
                lines = target.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                return ToolResult(success=False, error=f"'{path}' is not valid UTF-8 text")
            ln = line_number or 1
            if ln < 0 or ln > len(lines):
                return ToolResult(success=False, error=f"line_number {ln} is out of range (file has {len(lines)} lines)")
            insert_lines = content.splitlines()
            new_lines = lines[:ln] + insert_lines + lines[ln:]
            target.write_text("\n".join(new_lines) + ("\n" if target.read_text(encoding="utf-8").endswith("\n") else ""), encoding="utf-8")
            return ToolResult(success=True, output=f"Inserted {len(insert_lines)} line(s) after line {ln} in '{path}'.")

        if operation == "write":
            if content is None:
                return ToolResult(success=False, error="'content' is required for the 'write' operation")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                output=f"Wrote {len(content)} chars to '{path}'. "
                       f"If this is only part of the file, continue with 'append' calls.",
            )

        if operation == "append":
            if content is None:
                return ToolResult(success=False, error="'content' is required for the 'append' operation")
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"'{path}' does not exist — use 'write' to create it first, then 'append'.",
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("a", encoding="utf-8") as f:
                f.write(content)
            total_size = target.stat().st_size
            return ToolResult(
                success=True,
                output=f"Appended {len(content)} chars to '{path}' (file now {total_size} bytes total).",
            )

        if operation == "list":
            if not target.exists():
                return ToolResult(success=False, error=f"'{path}' does not exist")
            if target.is_file():
                return ToolResult(success=True, output=[target.name])
            entries = sorted(p.name + ("/" if p.is_dir() else "") for p in target.iterdir())
            return ToolResult(success=True, output=entries)

        if operation == "delete":
            if not target.exists():
                return ToolResult(success=False, error=f"'{path}' does not exist")
            if target.is_dir():
                return ToolResult(success=False, error=f"'{path}' is a directory — delete not supported for directories")
            target.unlink()
            return ToolResult(success=True, output=f"Deleted '{path}'")

        if operation == "exists":
            return ToolResult(success=True, output=target.exists())

        return ToolResult(success=False, error=f"Unknown operation '{operation}'")