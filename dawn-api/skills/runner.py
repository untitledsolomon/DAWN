"""
Runs a skill inside a Docker container with no access to DAWN's credentials,
DAWN's sandbox filesystem, or (by default) the network.

Protocol: args go in as JSON on stdin, the skill's entrypoint must print a
single JSON object (matching ToolResult's shape: success/output/error) to
stdout. Anything else on stdout is discarded; stderr is captured for
debugging but not trusted as output.

Isolation properties, all enforced here rather than assumed from the image:
  - no env vars passed through from DAWN's process (explicit empty env)
  - --network none unless the manifest explicitly requests network
  - --memory cap from the manifest
  - --pids-limit to stop fork-bombs
  - --read-only root filesystem, with only the skill's own repo dir writable
  - hard wall-clock timeout, container killed if exceeded
  - runs as a non-root user inside the container (--user)
"""
import asyncio
import json
import logging
from pathlib import Path
from tools.base import ToolResult
from skills.manifest import SkillManifest

logger = logging.getLogger(__name__)


async def run_skill_container(
    manifest: SkillManifest,
    repo_dir: Path,
    args: dict,
) -> ToolResult:
    container_name = f"dawn-skill-{manifest.name}-{id(args) & 0xffffff:x}"

    cmd = [
        "docker", "run",
        "--rm",
        "--name", container_name,
        "--user", "1000:1000",
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "--pids-limit", "128",
        "--memory", f"{manifest.memory_limit_mb}m",
        "--memory-swap", f"{manifest.memory_limit_mb}m",  # no swap beyond the memory cap
        "--cpus", "1.0",
        "--env-file", "/dev/null",  # explicitly no inherited env vars / secrets
        "-v", f"{repo_dir}:/skill:ro",  # skill's own code, read-only
        "-w", "/skill",
    ]

    if not manifest.network:
        cmd += ["--network", "none"]

    cmd += [manifest.image, "sh", "-c", manifest.entrypoint]

    logger.info(f"Launching skill container: {manifest.name} (network={manifest.network}, "
                f"mem={manifest.memory_limit_mb}mb, timeout={manifest.timeout_seconds}s)")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return ToolResult(success=False, error="Docker is not available on this host — cannot run skills.")

    stdin_payload = json.dumps(args).encode("utf-8")

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_payload),
            timeout=manifest.timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning(f"Skill '{manifest.name}' timed out after {manifest.timeout_seconds}s — killing container")
        await _force_kill(container_name)
        return ToolResult(success=False, error=f"Skill '{manifest.name}' timed out after {manifest.timeout_seconds}s")

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace")[-2000:]
        logger.warning(f"Skill '{manifest.name}' exited {proc.returncode}: {stderr_text}")
        return ToolResult(
            success=False,
            error=f"Skill '{manifest.name}' exited with code {proc.returncode}",
            metadata={"stderr": stderr_text},
        )

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    try:
        # Skill is expected to print exactly one JSON object as its last line of stdout
        last_line = stdout_text.splitlines()[-1] if stdout_text else ""
        parsed = json.loads(last_line)
    except (json.JSONDecodeError, IndexError):
        return ToolResult(
            success=False,
            error=f"Skill '{manifest.name}' did not return valid JSON output",
            metadata={"raw_stdout": stdout_text[-2000:]},
        )

    if not isinstance(parsed, dict) or "success" not in parsed:
        return ToolResult(
            success=False,
            error=f"Skill '{manifest.name}' output did not match the expected result shape",
            metadata={"raw_output": parsed},
        )

    return ToolResult(
        success=bool(parsed.get("success")),
        output=parsed.get("output"),
        error=parsed.get("error"),
        metadata={"skill": manifest.name},
    )


async def _force_kill(container_name: str) -> None:
    try:
        kill_proc = await asyncio.create_subprocess_exec(
            "docker", "kill", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await kill_proc.wait()
    except Exception:
        logger.exception(f"Failed to force-kill container {container_name}")
