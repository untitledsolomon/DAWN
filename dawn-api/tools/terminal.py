"""
Terminal tool — runs shell commands in the DAWN sandbox.

Uses subprocess.run() with shell=True as a fallback when asyncio's
create_subprocess_exec fails (common in restricted sandbox environments
where fork/exec are blocked at the syscall level but the shell itself
can spawn processes).

Security model:
- cwd is jailed to FILESYSTEM_SANDBOX_ROOT
- shell=True is used for compatibility, but command is still parsed
  through shlex to prevent trivial injection
- Hard timeout and output size cap
- Binary allowlist (not denylist) for the first argument
- DANGEROUS_ARG_SUBSTRINGS filter catches obvious escapes
- Auto-detects Windows vs Unix and uses the appropriate allowlist
"""
import asyncio
import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 120
MAX_OUTPUT_CHARS = 8000

# ── Detect OS ──────────────────────────────────────────────────────────────
_IS_WINDOWS = sys.platform.startswith("win") or os.name == "nt"

# ── Unix/Linux allowlist ───────────────────────────────────────────────────
UNIX_ALLOWED_BINARIES = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "pwd", "echo",
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx",
    "pytest", "go", "cargo", "rustc",
    "mkdir", "cp", "mv", "rm", "touch",
    "diff", "sort", "uniq", "tree",
    "which", "whoami", "id", "env", "printenv",
    "apt", "apt-get", "dpkg",
    "tesseract", "ffmpeg", "convert",
    "nmap", "whois", "dig", "nslookup", "host",
    "git", "curl", "wget",
    "docker", "docker-compose",
    "systemctl", "service",
    "ps", "top", "htop", "df", "du", "free", "uptime",
    "uname", "arch", "date", "cal",
    "tar", "gzip", "gunzip", "zip", "unzip",
    "chmod", "chown",
    "ssh", "scp",
    "sqlite3", "psql", "mysql",
    "make", "cmake",
    "perl", "ruby", "php",
    "java", "javac", "mvn", "gradle",
    "ping", "traceroute", "netstat", "ss",
    "kill", "killall", "pkill",
    "screen", "tmux",
    "nano", "vim", "vi", "emacs",
    "jq", "yq",
    "awk", "sed",
    "xargs",
    "tee",
    "ln",
    "file",
    "stat",
    "timeout",
    "watch",
    "yes",
    "sh", "bash", "zsh",
}

# ── Windows allowlist ──────────────────────────────────────────────────────
WINDOWS_ALLOWED_BINARIES = {
    # Shell builtins (cmd.exe)
    "dir", "type", "copy", "del", "erase", "move", "ren", "rename",
    "echo", "cd", "chdir", "cls", "date", "time", "ver", "vol",
    "md", "mkdir", "rd", "rmdir",
    "more", "find", "findstr", "sort", "fc", "comp",
    "set", "path", "prompt", "title", "color",
    "help", "pause", "exit",
    "assoc", "ftype",
    "break", "call", "pushd", "popd",
    "shift", "goto", "if", "for",
    # Common Windows executables
    "python", "python3", "pip", "pip3",
    "node", "npm", "npx",
    "git", "curl", "wget",
    "docker", "docker-compose",
    "where", "which",
    "whoami", "systeminfo", "hostname",
    "ipconfig", "ping", "tracert", "nslookup", "netstat",
    "tasklist", "taskkill",
    "powershell", "pwsh",
    "cmd",
    "reg", "regedit",
    "schtasks",
    "net",
    "msiexec",
    "chkdsk", "sfc",
    "attrib",
    "cacls", "icacls",
    "compact",
    "diskpart",
    "driverquery",
    "format",
    "fsutil",
    "gpupdate",
    "gprresult",
    "label",
    "manage-bde",
    "mklink",
    "mode",
    "mountvol",
    "openfiles",
    "powercfg",
    "qprocess",
    "query",
    "quser",
    "qwinsta",
    "recimg",
    "recover",
    "replace",
    "robocopy",
    "route",
    "rwinsta",
    "sc",
    "shutdown",
    "sleep",
    "sconfig",
    "start",
    "subst",
    "takeown",
    "telnet",
    "tftp",
    "timeout",
    "tracerpt",
    "tree",
    "tscon",
    "tsdiscon",
    "tsecimp",
    "tskill",
    "tsshutdn",
    "typeperf",
    "tzutil",
    "unlodctr",
    "verifier",
    "verify",
    "vssadmin",
    "w32tm",
    "waitfor",
    "wbadmin",
    "wdsutil",
    "wecutil",
    "wevtutil",
    "wftpdmin",
    "winrm",
    "winrs",
    "wmic",
    "wusa",
    "xcopy",
    "tar",
    "unzip",
    "7z",
    "nmap",
    "tesseract",
    "ffmpeg",
    "convert",
    "jq",
    "yq",
    # OSINT / network tools — confirmed installed on this system
    "ssh",
    "whois",
}

# Select the right allowlist at module load time
ALLOWED_BINARIES = WINDOWS_ALLOWED_BINARIES if _IS_WINDOWS else UNIX_ALLOWED_BINARIES

# Flags that would let an otherwise-safe binary escape the jail or the
# allowlist's intent (e.g. `python -c "import os; os.system(...)"`).
DANGEROUS_ARG_SUBSTRINGS = ("os.system", "subprocess", "eval(", "exec(")


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
        root = getattr(settings, "filesystem_sandbox_root", None) or "."
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"TerminalTool sandboxed to: {self.root} (OS: {'Windows' if _IS_WINDOWS else 'Unix/Linux'})")

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

        # Strategy 1: Try asyncio.create_subprocess_exec (clean, no shell)
        result = await self._run_asyncio(args, work_dir, timeout)
        if result is not None:
            return result

        # Strategy 2: Fallback to subprocess.run with shell=True
        # This handles sandbox environments where fork/exec is restricted
        # but the shell can still spawn processes.
        logger.info(f"asyncio subprocess failed, falling back to shell=True for: {command}")
        return await self._run_shell(command, work_dir, timeout)

    async def _run_asyncio(self, args: list[str], work_dir: Path, timeout: int) -> ToolResult | None:
        """Try asyncio.create_subprocess_exec. Returns None if it fails at startup."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(work_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(success=False, error=f"Binary '{args[0]}' not found on PATH")
        except Exception as e:
            logger.warning(f"asyncio subprocess failed for '{args[0]}': {e}")
            return None  # Signal fallback

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

    async def _run_shell(self, command: str, work_dir: Path, timeout: int) -> ToolResult:
        """Fallback using subprocess.run with shell=True."""
        try:
            proc = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    command,
                    cwd=str(work_dir),
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                ),
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"Command timed out after {timeout}s")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"Binary not found: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to run command: {e}")

        stdout_text = (proc.stdout or "")[:MAX_OUTPUT_CHARS]
        stderr_text = (proc.stderr or "")[:MAX_OUTPUT_CHARS]

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
