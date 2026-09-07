"""
Proxy tool for SKILL.md (knowledge) skills.

A SKILL.md skill is an instruction document, not an executable. When the
agent calls this tool, it returns the skill's full markdown body so the
agent can read and apply it — the same way Claude Code injects SKILL.md
content into its context. Optionally, if the skill declares a `run_command`
(e.g. an npx package), the tool can execute it inside an isolated container
and return the output.
"""
import asyncio
import json
import logging
from pathlib import Path
from tools.base import BaseTool, ToolResult
from skills.skillmd import SkillMDManifest

logger = logging.getLogger(__name__)


class SkillMDProxyTool(BaseTool):
    def __init__(self, manifest: SkillMDManifest, repo_dir: Path):
        self._manifest = manifest
        self._repo_dir = repo_dir
        self.name = f"skill_{manifest.name}"
        self.description = (
            f"[Knowledge skill] {manifest.description} "
            "Call this to load the skill's instructions and apply them to the "
            "current task. Returns the full skill guide as context."
        )
        # No input_schema — the skill is context, not a parameterized call.
        self.input_schema = {
            "type": "object",
            "properties": {},
        }

    async def run(self, **kwargs) -> ToolResult:
        # If the skill declares a run command and the agent passed args for it,
        # execute it in the container; otherwise return the instructions.
        if self._manifest.run_command and kwargs:
            return await self._run_command(kwargs)

        return ToolResult(
            success=True,
            output={
                "skill": self._manifest.name,
                "instructions": self._manifest.body,
            },
            metadata={"skill": self._manifest.name, "type": "knowledge"},
        )

    async def _run_command(self, args: dict) -> ToolResult:
        manifest = self._manifest
        container_name = f"dawn-skill-{manifest.name}-{id(args) & 0xffffff:x}"

        # Build the command: run_command is a template like
        # "npx some-package" and args are passed as flags/JSON.
        cmd_parts = manifest.run_command.split()
        for key, value in args.items():
            cmd_parts += [f"--{key}", str(value)]

        cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "--user", "1000:1000",
            "--read-only",
            "--tmpfs", "/tmp:size=64m",
            "--pids-limit", "128",
            "--memory", f"{manifest.memory_limit_mb}m",
            "--memory-swap", f"{manifest.memory_limit_mb}m",
            "--cpus", "1.0",
            "--env-file", "/dev/null",
            "-v", f"{self._repo_dir}:/skill:ro",
            "-w", "/skill",
        ]

        if not manifest.network:
            cmd += ["--network", "none"]

        cmd += [manifest.image, "sh", "-c", " ".join(cmd_parts)]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return ToolResult(success=False, error="Docker is not available on this host — cannot run skill command.")

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=manifest.timeout_seconds,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, error=f"Skill command timed out after {manifest.timeout_seconds}s")

        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=f"Skill command exited with code {proc.returncode}",
                metadata={"stderr": stderr.decode("utf-8", errors="replace")[-2000:]},
            )

        return ToolResult(
            success=True,
            output=stdout.decode("utf-8", errors="replace")[-8000:],
            metadata={"skill": manifest.name},
        )
