"""
Skill installer, exposed to the LLM as a tool ('install_skill') so it can
autonomously extend its own capabilities mid-task, per the original design
goal. The trust boundary is enforced structurally, not by asking the LLM
nicely:

  - This module clones the repo and reads skill.yaml. That's it.
  - It NEVER imports, execs, or evals anything from the cloned repo.
  - The only thing ever executed from the repo is manifest.entrypoint,
    and that only ever runs inside the locked-down container built in
    skills/runner.py — never in DAWN's own process.
  - A newly installed skill is immediately usable in the same agent loop
    that installed it (the registry is mutated in place), matching the
    "autonomous mid-task" requirement.
"""
from pathlib import Path
import logging
import shutil
from tools.base import BaseTool, ToolResult
from tools.registry import get_registry
from skills.manifest import parse_manifest, ManifestError
from skills.proxy_tool import SkillProxyTool
from config import settings

logger = logging.getLogger(__name__)


def _skills_dir() -> Path:
    # Deliberately separate from filesystem_sandbox_root — skill repos are a
    # different trust tier than user-facing sandbox files and shouldn't share
    # a directory tree with them.
    root = getattr(settings, "skills_install_root", None) or "./installed_skills"
    path = Path(root).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path

def _is_local_path(source: str) -> bool:
    """Anything that isn't an http(s) URL is treated as a sandbox-relative path."""
    return not (source.startswith("https://") or source.startswith("http://"))


def _resolve_local_skill_path(rel_path: str) -> Path | None:
    """Resolve against filesystem_sandbox_root, refusing escapes — same pattern as FilesystemTool/GitTool."""
    root = Path(getattr(settings, "filesystem_sandbox_root", None) or "./sandbox").resolve()
    candidate = (root / rel_path).resolve()
    if root not in candidate.parents and candidate != root:
        return None
    return candidate

class SkillInstallTool(BaseTool):
    name = "install_skill"
    description = (
        "Install a new capability from a GitHub repository URL, or from a "
        "local directory already inside the DAWN sandbox (e.g. a skill you "
        "just wrote with the filesystem tool). The source must contain a "
        "valid skill.yaml manifest at its root. Once installed, the skill "
        "becomes available as a new tool (named 'skill_<name>') for the "
        "rest of this task. Only use this when an existing tool genuinely "
        "cannot do what's needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": (
                    "Either an HTTPS GitHub repo URL (clones it), or a path "
                    "relative to the sandbox root (e.g. 'skills/web-design') "
                    "for a skill you've already written locally."
                ),
            },
        },
        "required": ["repo_url"],
    }

    async def run(self, repo_url: str) -> ToolResult:
        import asyncio
        from git import Repo, GitCommandError

        if _is_local_path(repo_url):
            target = _resolve_local_skill_path(repo_url)
            if target is None:
                return ToolResult(
                    success=False,
                    error=(
                        f"'{repo_url}' does not resolve to a directory inside the "
                        "sandbox. Local skill sources must be a path relative to "
                        "the sandbox root — write the skill there first."
                    ),
                )
            if not target.is_dir():
                return ToolResult(success=False, error=f"'{repo_url}' is not a directory")
            logger.info(f"Installing skill from local sandbox path: {target}")
        else:
            skills_dir = _skills_dir()
            folder_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
            folder_name = "".join(c for c in folder_name if c.isalnum() or c in "-_") or "skill"
            target = skills_dir / folder_name

            if target.exists():
                logger.info(f"Skill repo already cloned at {target} — reusing")
            else:
                try:
                    await asyncio.to_thread(Repo.clone_from, repo_url, target, depth=1)
                except GitCommandError as e:
                    return ToolResult(success=False, error=f"Failed to clone '{repo_url}': {e}")
                except Exception as e:
                    return ToolResult(success=False, error=f"Failed to clone '{repo_url}': {e}")

        try:
            manifest = parse_manifest(target)
        except ManifestError as e:
            # Only clean up clones — never delete a local sandbox dir the
            # user wrote themselves just because the manifest was bad.
            if not _is_local_path(repo_url):
                shutil.rmtree(target, ignore_errors=True)
            return ToolResult(success=False, error=f"Invalid skill manifest: {e}")

        registry = get_registry()
        proxy = SkillProxyTool(manifest, target)
        registry.register(proxy)

        logger.info(
            f"Installed skill '{manifest.name}' from {repo_url} "
            f"(network={manifest.network}, image={manifest.image})"
        )

        return ToolResult(
            success=True,
            output=(
                f"Installed skill '{manifest.name}' as tool '{proxy.name}'. "
                f"{manifest.description} It's now available to call."
            ),
            metadata={
                "skill_name": manifest.name,
                "tool_name": proxy.name,
                "network_enabled": manifest.network,
                "source": "local" if _is_local_path(repo_url) else "remote",
            },
        )