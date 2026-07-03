"""
Wraps an installed skill as a normal BaseTool. From the agent loop and
registry's perspective, an installed skill is indistinguishable from
filesystem/git/web_search — the isolation happens entirely inside
skills.runner and is invisible above this layer.
"""
from pathlib import Path
from tools.base import BaseTool, ToolResult
from skills.manifest import SkillManifest
from skills.runner import run_skill_container


class SkillProxyTool(BaseTool):
    def __init__(self, manifest: SkillManifest, repo_dir: Path):
        self._manifest = manifest
        self._repo_dir = repo_dir
        self.name = f"skill_{manifest.name}"
        self.description = f"[Installed skill] {manifest.description}"
        self.input_schema = manifest.input_schema

    async def run(self, **kwargs) -> ToolResult:
        return await run_skill_container(self._manifest, self._repo_dir, kwargs)
