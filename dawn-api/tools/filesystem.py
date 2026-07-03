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

logger = logging.getLogger(__name__)


class FilesystemTool(BaseTool):
    name = "filesystem"
    description = (
        "Read, write, list, or delete files within the DAWN sandbox directory. "
        "All paths are relative to the sandbox root — you cannot access files outside it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["read", "write", "list", "delete", "exists"],
                "description": "The filesystem operation to perform.",
            },
            "path": {
                "type": "string",
                "description": "Path relative to the sandbox root, e.g. 'projects/foo/notes.md'.",
            },
            "content": {
                "type": "string",
                "description": "Content to write. Required for the 'write' operation, ignored otherwise.",
            },
        },
        "required": ["operation", "path"],
    }

    def __init__(self):
        root = getattr(settings, "filesystem_sandbox_root", None) or "./sandbox"
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"FilesystemTool sandboxed to: {self.root}")

    def _resolve(self, path: str) -> Path:
        """Resolve a user-supplied relative path against the sandbox root, refusing escapes."""
        candidate = (self.root / path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"Path '{path}' escapes the sandbox root")
        return candidate

    async def run(self, operation: str, path: str, content: str | None = None) -> ToolResult:
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

        if operation == "write":
            if content is None:
                return ToolResult(success=False, error="'content' is required for the 'write' operation")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Wrote {len(content)} bytes to '{path}'")

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
