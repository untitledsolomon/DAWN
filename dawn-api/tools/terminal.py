"""
Terminal tool — runs shell commands, but not really "arbitrary shell":
- cwd is jailed to FILESYSTEM_SANDBOX_ROOT (same boundary as filesystem/git)
- no shell=True — args are passed as a list, so ; | && $() etc. are inert
  characters in an argument, not shell syntax. This kills the most common
  injection-via-tool-output vector (a fetched web page or repo README
  containing "; rm -rf /" does nothing here).
- hard timeout, output size cap, and a binary allowlist rather than a
  denylist — denylists always miss something.
Mirrors GitTool/FilesystemTool's sandbox pattern; see tools/git.py for the
reasoning on why push/remote-config were deliberately left out there. Same
philosophy here: start narrow, expand one verified case at a time.
"""
import asyncio
import logging
import shlex
from pathlib import Path
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 8000

# Allowlist, not denylist. Deliberately excludes anything that can move
# data off-box (curl/wget/nc/ssh/scp — use web_fetch/git for that, which
# have their own SSRF/scope guards), edit permissions (chmod/chown), or
# spawn a shell (bash/sh/python -c with a shell escape hatch).
ALLOWED_BINARIES = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "pwd", "echo",
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "pytest", "go", "cargo", "rustc",
    "mkdir", "cp", "mv", "rm", "touch",
    "diff", "sort", "uniq", "tree",
}

# Flags that would let an otherwise-safe binary escape the jail or the
# allowlist's intent (e.g. `python -c "import os; os.system(...)"`).
DANGEROUS_ARG_SUBSTRINGS = ("-c", "--command", "os.system", "subprocess", "eval(", "exec(")


class TerminalTool(BaseTool):
    name = "terminal"
    description = (
        "Run a shell command inside the DAWN sandbox directory. Use for "
        "inspecting files, running tests, checking build/lint output, or "
        "installing packages needed for a task. Commands run with a "
        "restricted binary set and no shell interpretation — pipes, "
        "redirects, and command chaining (| ; && $()) are not supported; "
        "run one command per call instead."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "The command to run, e.g. 'pytest tests/ -v' or 'npm install'. "
                    "Parsed as a single command with arguments — no shell operators."
                ),
            },
            "cwd": {
                "type": "string",
                "description": "Working directory relative to the sandbox root. Defaults to the root itself.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": f"Max seconds to allow. Defaults to {DEFAULT_TIMEOUT_SECONDS}, capped at {MAX_TIMEOUT_SECONDS}.",
            },
        },
        "required": ["command"],
    }

    def __init__(self):
        root = getattr(settings, "filesystem_sandbox_root", None) or "./sandbox"
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"TerminalTool sandboxed to: {self.root}")

    def _resolve_cwd(self, cwd: str | None) -> Path:
        if not cwd:
            return self.root
        candidate = (self.root / cwd).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"cwd '{cwd}' escapes the sandbox root")
        if not candidate.is_dir():
            raise ValueError(f"cwd '{cwd}' does not exist or is not a directory")
        return candidate

    async def run(
        self,
        command: str,
        cwd: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> ToolResult:
        try:
            args = shlex.split(command)
        except ValueError as e:
            return ToolResult(success=False, error=f"Could not parse command: {e}")

        if not args:
            return ToolResult(success=False, error="Empty command")

        binary = args[0]
        if binary not in ALLOWED_BINARIES:
            return ToolResult(
                success=False,
                error=(
                    f"'{binary}' is not in the allowed binary set. Allowed: "
                    f"{', '.join(sorted(ALLOWED_BINARIES))}"
                ),
            )

        joined = " ".join(args)
        for bad in DANGEROUS_ARG_SUBSTRINGS:
            if bad in joined:
                return ToolResult(
                    success=False,
                    error=f"Command rejected — contains disallowed pattern '{bad}'",
                )

        try:
            work_dir = self._resolve_cwd(cwd)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

        timeout = min(max(1, timeout_seconds), MAX_TIMEOUT_SECONDS)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # No shell=True, no env passthrough of secrets beyond what's
                # already in the process env — this is a subprocess, not a shell.
            )
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Binary '{binary}' not found on PATH")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to start command: {e}")

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(success=False, error=f"Command timed out after {timeout}s and was killed")

        stdout_text = stdout.decode(errors="replace")[:MAX_OUTPUT_CHARS]
        stderr_text = stderr.decode(errors="replace")[:MAX_OUTPUT_CHARS]

        return ToolResult(
            success=proc.returncode == 0,
            output={
                "stdout": stdout_text,
                "stderr": stderr_text,
                "returncode": proc.returncode,
                "cwd": str(work_dir.relative_to(self.root)) or ".",
            },
            error=None if proc.returncode == 0 else f"Exited with code {proc.returncode}",
        )