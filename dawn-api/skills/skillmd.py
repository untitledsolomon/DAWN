"""
SKILL.md skill support.

Claude Code-style skills (as found in the ECC library and many other
repos) are markdown files with YAML frontmatter — they are *instructions*
the agent reads and applies, not executable containers. This module parses
a SKILL.md into a lightweight manifest so DAWN can register it as a
knowledge skill.

The frontmatter carries the metadata:

    ---
    name: api-design
    description: REST API design patterns...
    ---

    # Body
    ...markdown instructions...

There is no `input_schema` or `entrypoint` — the skill is surfaced to the
agent as context to follow, exactly as Claude Code injects it. This is a
deliberate second path alongside the container-based skill.yaml skills in
skills/manifest.py: SKILL.md skills never execute code; they guide the
agent.
"""
from dataclasses import dataclass
from pathlib import Path
import logging
import re

logger = logging.getLogger(__name__)


@dataclass
class SkillMDManifest:
    name: str
    description: str
    body: str
    # Optional: a command to run the skill's tooling (e.g. an npx package).
    # When present, the proxy tool can offer to run it via the container.
    run_command: str | None = None
    image: str = "node:20-slim"
    network: bool = True
    timeout_seconds: int = 120
    memory_limit_mb: int = 512


class SkillMDError(ValueError):
    pass


def parse_skill_md(repo_dir: Path) -> SkillMDManifest:
    """
    Find and parse a SKILL.md at the repo root (or in a `.agents/skills/`
    subdirectory). Raises SkillMDError if none is found or the frontmatter
    is malformed.
    """
    candidates = [
        repo_dir / "SKILL.md",
        repo_dir / ".agents" / "skills" / "SKILL.md",
    ]
    # ECC-style layout: skills live at .agents/skills/<skill-name>/SKILL.md.
    if (repo_dir / ".agents" / "skills").is_dir():
        candidates += sorted((repo_dir / ".agents" / "skills").glob("*/SKILL.md"))

    skill_path = next((c for c in candidates if c.is_file()), None)
    if skill_path is None:
        raise SkillMDError(f"No SKILL.md found at repo root or .agents/skills/ ({repo_dir})")

    text = skill_path.read_text(encoding="utf-8")

    # Parse YAML frontmatter: a block delimited by --- at the very start.
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not frontmatter_match:
        raise SkillMDError(f"SKILL.md at {skill_path} has no YAML frontmatter block")

    frontmatter = frontmatter_match.group(1)
    body = text[frontmatter_match.end():].strip()

    try:
        import yaml
    except ImportError:
        raise SkillMDError("PyYAML is required to parse SKILL.md frontmatter")

    try:
        meta = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError as e:
        raise SkillMDError(f"SKILL.md frontmatter is not valid YAML: {e}")

    if not isinstance(meta, dict):
        raise SkillMDError("SKILL.md frontmatter must be a YAML mapping")

    name = str(meta.get("name", "")).strip()
    description = str(meta.get("description", "")).strip()

    if not name:
        raise SkillMDError(f"SKILL.md at {skill_path} is missing a 'name' in frontmatter")
    if not description:
        raise SkillMDError(f"SKILL.md at {skill_path} is missing a 'description' in frontmatter")

    safe_name = name
    if not all(c.isalnum() or c in "-_" for c in safe_name):
        raise SkillMDError("'name' may only contain letters, numbers, '-' and '_'")

    # Optional: a run command (e.g. "npx some-package") declared in frontmatter.
    run_command = meta.get("run_command")
    if run_command is not None and not isinstance(run_command, str):
        raise SkillMDError("'run_command' must be a string")

    return SkillMDManifest(
        name=safe_name,
        description=description,
        body=body,
        run_command=run_command,
        image=str(meta.get("image", "node:20-slim")),
        network=bool(meta.get("network", True)),
        timeout_seconds=int(meta.get("timeout_seconds", 120)),
        memory_limit_mb=int(meta.get("memory_limit_mb", 512)),
    )
