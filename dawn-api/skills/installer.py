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


class SkillInstallTool(BaseTool):
    name = "install_skill"
    description = (
        "Install a new capability from a GitHub repository. The repo must contain "
        "a valid skill.yaml manifest at its root. Once installed, the skill becomes "
        "available as a new tool (named 'skill_<name>') for the rest of this task. "
        "Only use this when an existing tool genuinely cannot do what's needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": "HTTPS URL of the GitHub repository to install as a skill.",
            },
        },
        "required": ["repo_url"],
    }

    async def run(self, repo_url: str) -> ToolResult:
        import asyncio
        from git import Repo, GitCommandError

        skills_dir = _skills_dir()

        # Derive a filesystem-safe folder name from the URL rather than trusting
        # anything skill-supplied at this stage — we haven't read the manifest yet.
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
            # Clean up the clone if the manifest is invalid — don't leave
            # unvalidated repos sitting around.
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
            },
        )
