"""
npx tool — run an npx package in an isolated container.

Many skills and utilities ship as npm packages runnable via `npx` (e.g.
`npx prettier`, `npx eslint`, `npx tsx`, `npx @some/cli`). This tool runs
an npx command inside a locked-down node container with no access to
DAWN's credentials, sandbox filesystem, or (by default) the network —
the same isolation model as skills/runner.py.

The command is parsed as a single command with arguments (no shell
operators), matching TerminalTool's safety posture.
"""
import asyncio
import logging
import shlex
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# npx packages that are known to be safe/expected; the tool is gated to
# these so the model can't run arbitrary remote code. Add packages here as
# they're validated.
ALLOWED_NPX_PACKAGES = {
    "prettier",
    "eslint",
    "tsx",
    "typescript",
    "tsc",
    "vitest",
    "jest",
    "next",
    "prisma",
    "zod",
    "claude-code",
    "@modelcontextprotocol/inspector",
}


class NpxTool(BaseTool):
    name = "npx"
    description = (
        "Run an npx package inside an isolated container. Use for npm "
        "packages that provide CLI tools (prettier, eslint, tsx, vitest, "
        "prisma, etc.). The command runs in a locked-down node container "
        "with no network by default. Only a curated set of packages is "
        "allowed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "package": {
                "type": "string",
                "description": "The npx package to run (e.g. 'prettier', 'eslint', 'tsx').",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Arguments to pass to the package, e.g. ['--check', 'file.ts'].",
            },
            "network": {
                "type": "boolean",
                "description": "Allow network access (needed to install the package). Default false.",
                "default": False,
            },
        },
        "required": ["package", "args"],
    }

    async def run(self, package: str, args: list[str], network: bool = False) -> ToolResult:
        package = package.strip()
        if package not in ALLOWED_NPX_PACKAGES:
            return ToolResult(
                success=False,
                error=(
                    f"Package '{package}' is not in the allowed npx allowlist. "
                    f"Allowed: {', '.join(sorted(ALLOWED_NPX_PACKAGES))}."
                ),
            )

        # Validate args — no shell metacharacters.
        for a in args:
            if any(c in a for c in "|;&$()<>`"):
                return ToolResult(success=False, error="Arguments may not contain shell operators.")

        cmd = [
            "docker", "run",
            "--rm",
            "--user", "1000:1000",
            "--read-only",
            "--tmpfs", "/tmp:size=128m",
            "--pids-limit", "128",
            "--memory", "1024m",
            "--memory-swap", "1024m",
            "--cpus", "1.0",
            "--env-file", "/dev/null",
            "--workdir", "/work",
            "node:20-slim",
            "sh", "-c",
            f"npx --yes {package} {' '.join(shlex.quote(a) for a in args)}",
        ]

        if not network:
            cmd += ["--network", "none"]

        logger.info(f"Running npx {package} (network={network})")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(success=False, error="Docker is not available on this host — cannot run npx.")

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="npx command timed out after 120s")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"npx {package} exited with code {proc.returncode}",
                metadata={"stderr": stderr.decode("utf-8", errors="replace")[-2000:]},
            )

        return ToolResult(
            success=True,
            output=stdout.decode("utf-8", errors="replace")[-8000:],
            metadata={"package": package},
        )
