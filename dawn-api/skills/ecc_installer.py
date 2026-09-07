"""
ECC skill installer.

The ECC repo (github.com/untitledsolomon/ECC) is a large library of
SKILL.md knowledge skills (~900 of them) laid out at
`.agents/skills/<skill-name>/SKILL.md`. This tool lets the agent install a
single skill from that library by name without cloning the whole repo —
it fetches just that skill's SKILL.md over the GitHub API and registers it
as a knowledge skill (see skills/skillmd_proxy.py).

The trust boundary matches the rest of the skill system: only the SKILL.md
markdown is fetched and read. It is never imported, exec'd, or eval'd —
it is surfaced to the agent as instructions to follow.
"""
import asyncio
import json
import logging
import urllib.request
from pathlib import Path
from tools.base import BaseTool, ToolResult
from tools.registry import get_registry
from skills.skillmd import parse_skill_md, SkillMDError
from skills.skillmd_proxy import SkillMDProxyTool
from config import settings

logger = logging.getLogger(__name__)

ECC_REPO = "untitledsolomon/ECC"
ECC_SKILLS_PATH = ".agents/skills"


def _skills_dir() -> Path:
    root = getattr(settings, "skills_install_root", None) or "./installed_skills"
    path = Path(root).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fetch_skill_md(skill_name: str) -> str:
    """Fetch a single SKILL.md from the ECC repo via the GitHub API."""
    url = (
        f"https://raw.githubusercontent.com/{ECC_REPO}/main/"
        f"{ECC_SKILLS_PATH}/{skill_name}/SKILL.md"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "DAWN"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


class InstallECCSkillTool(BaseTool):
    name = "install_ecc_skill"
    description = (
        "Install a knowledge skill from the ECC skill library "
        "(github.com/untitledsolomon/ECC) by name. The ECC library contains "
        "hundreds of SKILL.md instruction skills (api-design, deep-research, "
        "mcp-server-patterns, coding-standards, etc.). Pass the skill name "
        "and it becomes available as a tool ('skill_<name>') that loads the "
        "skill's instructions for you to apply. Use when you need guidance "
        "from the ECC library for the current task."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Name of the ECC skill to install (e.g. 'api-design', 'deep-research').",
            },
        },
        "required": ["skill_name"],
    }

    async def run(self, skill_name: str) -> ToolResult:
        skill_name = skill_name.strip().strip("/")
        if not skill_name or not all(c.isalnum() or c in "-_" for c in skill_name):
            return ToolResult(success=False, error="Invalid skill name — use only letters, numbers, '-' and '_'.")

        # Cache the fetched skill under the skills install root so we don't
        # re-download on every call.
        skills_dir = _skills_dir()
        skill_dir = skills_dir / f"ecc_{skill_name}"
        skill_md_path = skill_dir / "SKILL.md"

        if not skill_md_path.is_file():
            try:
                content = await asyncio.to_thread(_fetch_skill_md, skill_name)
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=(
                        f"Failed to fetch ECC skill '{skill_name}': {e}. "
                        "Check the name is correct — it must match a directory "
                        f"under {ECC_SKILLS_PATH}/ in the ECC repo."
                    ),
                )
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_md_path.write_text(content, encoding="utf-8")

        try:
            manifest = parse_skill_md(skill_dir)
        except SkillMDError as e:
            return ToolResult(success=False, error=f"Invalid ECC skill: {e}")

        registry = get_registry()
        proxy = SkillMDProxyTool(manifest, skill_dir)
        registry.register(proxy)

        logger.info(f"Installed ECC knowledge skill '{manifest.name}' from ECC library")

        return ToolResult(
            success=True,
            output=(
                f"Installed ECC knowledge skill '{manifest.name}' as tool "
                f"'{proxy.name}'. {manifest.description} Call it to load the "
                f"skill's instructions and apply them to the current task."
            ),
            metadata={
                "skill_name": manifest.name,
                "tool_name": proxy.name,
                "skill_type": "knowledge",
                "source": "ecc",
            },
        )
