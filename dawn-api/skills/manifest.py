"""
Skill manifest contract.

Every installable skill repo must contain a `skill.yaml` at its root:

    name: pdf-summarizer
    description: Summarizes PDF documents into key points.
    input_schema:
      type: object
      properties:
        file_path: {type: string, description: "Path to the PDF, relative to skill workdir"}
      required: [file_path]
    entrypoint: "python run.py"     # command run *inside* the container
    image: "python:3.12-slim"        # base image; skill's own Dockerfile takes priority if present
    network: false                   # does this skill need outbound network access?
    timeout_seconds: 60
    memory_limit_mb: 512

DAWN's core NEVER imports or executes any file from the skill repo directly.
The manifest is the only thing DAWN's trusted process reads and trusts; the
`entrypoint` command is only ever executed inside the isolated container,
never in DAWN's own process or environment.
"""
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["name", "description", "input_schema", "entrypoint"]


@dataclass
class SkillManifest:
    name: str
    description: str
    input_schema: dict
    entrypoint: str
    image: str = "python:3.12-slim"
    network: bool = False
    timeout_seconds: int = 60
    memory_limit_mb: int = 512
    dockerfile_present: bool = False


class ManifestError(ValueError):
    pass


def parse_manifest(repo_dir: Path) -> SkillManifest:
    """
    Read and validate skill.yaml from a cloned repo. Raises ManifestError on
    anything malformed or missing — installation must fail closed, not
    guess at defaults for required fields.
    """
    import yaml  # PyYAML — add to requirements.txt if not already present

    manifest_path = repo_dir / "skill.yaml"
    if not manifest_path.is_file():
        raise ManifestError(f"No skill.yaml found at repo root ({repo_dir})")

    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ManifestError(f"skill.yaml is not valid YAML: {e}")

    if not isinstance(raw, dict):
        raise ManifestError("skill.yaml must be a YAML mapping at the top level")

    missing = [f for f in REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ManifestError(f"skill.yaml is missing required fields: {', '.join(missing)}")

    if not isinstance(raw["name"], str) or not raw["name"].strip():
        raise ManifestError("'name' must be a non-empty string")
    # Restrict name to something safe to use as a container name / registry key
    safe_name = raw["name"].strip()
    if not all(c.isalnum() or c in "-_" for c in safe_name):
        raise ManifestError("'name' may only contain letters, numbers, '-' and '_'")

    if not isinstance(raw["input_schema"], dict):
        raise ManifestError("'input_schema' must be a JSON-schema-shaped mapping")

    dockerfile_present = (repo_dir / "Dockerfile").is_file()

    timeout = raw.get("timeout_seconds", 60)
    memory = raw.get("memory_limit_mb", 512)
    if not isinstance(timeout, int) or timeout <= 0 or timeout > 600:
        raise ManifestError("'timeout_seconds' must be an int between 1 and 600")
    if not isinstance(memory, int) or memory <= 0 or memory > 4096:
        raise ManifestError("'memory_limit_mb' must be an int between 1 and 4096")

    return SkillManifest(
        name=safe_name,
        description=str(raw["description"]),
        input_schema=raw["input_schema"],
        entrypoint=str(raw["entrypoint"]),
        image=str(raw.get("image", "python:3.12-slim")),
        network=bool(raw.get("network", False)),
        timeout_seconds=timeout,
        memory_limit_mb=memory,
        dockerfile_present=dockerfile_present,
    )
