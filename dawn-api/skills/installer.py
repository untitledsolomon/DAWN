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
from skills.skillmd import parse_skill_md, SkillMDError
from skills.skillmd_proxy import SkillMDProxyTool
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


def _raw_file_url(source: str) -> str | None:
    """If `source` is a GitHub URL pointing directly at a skill file
    (SKILL.md or skill.yaml), return a raw.githubusercontent.com URL to fetch
    just that file. Returns None if the URL is a repo URL (to be cloned).

    Accepts:
      - https://github.com/<owner>/<repo>/blob/<branch>/<path>/SKILL.md
      - https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>/SKILL.md
    """
    source = source.strip()
    if source.endswith(".git"):
        return None
    if "github.com/" not in source and "raw.githubusercontent.com/" not in source:
        return None
    # Normalize github.com blob URLs to raw.githubusercontent.com URLs.
    if "github.com/" in source:
        if "/blob/" not in source:
            return None  # a repo URL, not a direct file link — clone it
        source = source.replace("/blob/", "/")
        source = source.replace("github.com/", "raw.githubusercontent.com/", 1)
    if not source.startswith("https://raw.githubusercontent.com/"):
        return None
    # Only treat as a single-file fetch if it points at a skill manifest file.
    lower = source.lower()
    if not (lower.endswith("skill.md") or lower.endswith("skill.yaml") or lower.endswith("skill.yml")):
        return None
    return source


def _fetch_raw_skill(raw_url: str, folder_name: str) -> Path | None:
    """Download a single skill file (SKILL.md or skill.yaml) into the skills
    dir. Returns the target directory, or None on failure."""
    import urllib.request
    skills_dir = _skills_dir()
    folder_name = "".join(c for c in folder_name if c.isalnum() or c in "-_") or "skill"
    target = skills_dir / folder_name
    target.mkdir(parents=True, exist_ok=True)
    filename = "SKILL.md" if raw_url.lower().endswith("skill.md") else "skill.yaml"
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "DAWN"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read().decode("utf-8")
        (target / filename).write_text(content, encoding="utf-8")
        return target
    except Exception as e:
        logger.warning(f"Failed to fetch raw skill {raw_url}: {e}")
        return None


class SkillInstallTool(BaseTool):
    name = "install_skill"
    description = (
        "Install a new capability from a GitHub repository URL, a direct "
        "link to a SKILL.md or skill.yaml file, or from a local directory "
        "already inside the DAWN sandbox. The source must contain either a "
        "valid skill.yaml manifest (container-executed skill) or a SKILL.md "
        "file (knowledge skill, the Claude Code format used by the ECC "
        "library). Once installed, the skill becomes available as a new tool "
        "(named 'skill_<name>') for the rest of this task. Only use this when "
        "an existing tool genuinely cannot do what's needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "repo_url": {
                "type": "string",
                "description": (
                    "Either an HTTPS GitHub repo URL (clones it), a direct "
                    "link to a SKILL.md or skill.yaml file on GitHub "
                    "(e.g. https://github.com/<owner>/<repo>/blob/main/SKILL.md "
                    "or .../path/to/SKILL.md), or a path relative to the "
                    "sandbox root (e.g. 'skills/web-design') for a skill "
                    "you've already written locally."
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
            # A raw GitHub URL pointing directly at a SKILL.md / skill.yaml
            # file — fetch just that file instead of cloning the whole repo.
            raw_url = _raw_file_url(repo_url)
            if raw_url is not None:
                # Derive a folder name from the file's parent directory
                # (e.g. .../api-design/SKILL.md -> api-design). If the file is
                # at the repo root (e.g. .../main/skill.yaml), fall back to a
                # sanitized name from the repo.
                parts = raw_url.rstrip("/").split("/")
                folder_name = parts[-2] if parts[-2] not in ("main", "master") else parts[-3]
                target = await asyncio.to_thread(_fetch_raw_skill, raw_url, folder_name)
                if target is None:
                    return ToolResult(success=False, error=f"Failed to fetch skill from '{repo_url}'")
                logger.info(f"Installed skill from raw file URL: {repo_url}")
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

        # Two skill formats are supported:
        #   1. skill.yaml — container-executed skills (skills/manifest.py)
        #   2. SKILL.md — knowledge/instruction skills (skills/skillmd.py),
        #      the Claude Code format used by the ECC library and others.
        # Try the container format first; fall back to SKILL.md.
        try:
            manifest = parse_manifest(target)
        except ManifestError as yaml_err:
            try:
                skillmd = parse_skill_md(target)
            except SkillMDError as md_err:
                # Only clean up clones — never delete a local sandbox dir the
                # user wrote themselves just because the manifest was bad.
                if not _is_local_path(repo_url):
                    shutil.rmtree(target, ignore_errors=True)
                return ToolResult(
                    success=False,
                    error=(
                        f"Invalid skill source: no valid skill.yaml ({yaml_err}) "
                        f"or SKILL.md ({md_err})."
                    ),
                )
            # SKILL.md knowledge skill
            registry = get_registry()
            proxy = SkillMDProxyTool(skillmd, target)
            registry.register(proxy)
            logger.info(
                f"Installed knowledge skill '{skillmd.name}' from {repo_url} "
                f"(SKILL.md, run_command={skillmd.run_command!r})"
            )
            return ToolResult(
                success=True,
                output=(
                    f"Installed knowledge skill '{skillmd.name}' as tool "
                    f"'{proxy.name}'. {skillmd.description} Call it to load the "
                    f"skill's instructions and apply them."
                ),
                metadata={
                    "skill_name": skillmd.name,
                    "tool_name": proxy.name,
                    "skill_type": "knowledge",
                    "run_command": skillmd.run_command,
                    "source": "local" if _is_local_path(repo_url) else "remote",
                },
            )

        # skill.yaml container skill
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