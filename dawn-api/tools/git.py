"""
Git tool — operates only within FILESYSTEM_SANDBOX_ROOT, same trust boundary
as FilesystemTool. Wraps GitPython (already in requirements.txt).

Deliberately does NOT expose push, remote add/set-url, or arbitrary raw git
commands. Those are the operations most likely to (a) exfiltrate the sandbox
contents somewhere, or (b) mutate infra outside DAWN's control. Add them
later, individually, once there's a concrete need — not as a blanket
"run any git command" escape hatch.
"""
from pathlib import Path
import logging
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

MAX_CLONE_DEPTH = 1  # shallow clone by default — keep this cheap and fast


class GitTool(BaseTool):
    name = "git"
    description = (
        "Clone, inspect, and commit to git repositories within the DAWN sandbox. "
        "Supports: clone, status, log, diff, add, commit, branch, checkout. "
        "Does not support push or remote configuration."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["clone", "status", "log", "diff", "add", "commit", "branch", "checkout"],
                "description": "The git operation to perform.",
            },
            "path": {
                "type": "string",
                "description": (
                    "For 'clone': the destination directory (relative to sandbox root) to clone into. "
                    "For all other operations: the path to an existing repo (relative to sandbox root)."
                ),
            },
            "url": {
                "type": "string",
                "description": "Repository URL. Required for 'clone'.",
            },
            "message": {
                "type": "string",
                "description": "Commit message. Required for 'commit'.",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files to stage, relative to the repo root. Required for 'add'. Use ['.'] for all.",
            },
            "branch_name": {
                "type": "string",
                "description": "Branch to create or check out. Required for 'branch' and 'checkout'.",
            },
            "log_limit": {
                "type": "integer",
                "description": "Max number of commits to return for 'log'. Defaults to 10.",
            },
        },
        "required": ["operation", "path"],
    }

    def __init__(self):
        root = getattr(settings, "filesystem_sandbox_root", None) or "./sandbox"
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(f"GitTool sandboxed to: {self.root}")

    def _resolve(self, path: str) -> Path:
        candidate = (self.root / path).resolve()
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError(f"Path '{path}' escapes the sandbox root")
        return candidate

    async def run(
        self,
        operation: str,
        path: str,
        url: str | None = None,
        message: str | None = None,
        files: list[str] | None = None,
        branch_name: str | None = None,
        log_limit: int = 10,
    ) -> ToolResult:
        import asyncio

        try:
            target = self._resolve(path)
        except ValueError as e:
            return ToolResult(success=False, error=str(e))

        # Run the actual (blocking) GitPython call in a thread so we don't
        # stall the event loop — same reasoning as filesystem ops, but git
        # operations (especially clone) can take real wall-clock time.
        try:
            return await asyncio.to_thread(
                self._run_sync, operation, target, path, url, message, files, branch_name, log_limit
            )
        except Exception as e:
            logger.exception(f"git {operation} failed")
            return ToolResult(success=False, error=f"git {operation} failed: {e}")

    def _run_sync(
        self,
        operation: str,
        target: Path,
        rel_path: str,
        url: str | None,
        message: str | None,
        files: list[str] | None,
        branch_name: str | None,
        log_limit: int,
    ) -> ToolResult:
        import git
        from git import Repo, GitCommandError

        if operation == "clone":
            if not url:
                return ToolResult(success=False, error="'url' is required for 'clone'")
            if target.exists() and any(target.iterdir()):
                return ToolResult(success=False, error=f"'{rel_path}' already exists and is not empty")
            try:
                Repo.clone_from(url, target, depth=MAX_CLONE_DEPTH)
            except GitCommandError as e:
                return ToolResult(success=False, error=f"Clone failed: {e}")
            return ToolResult(success=True, output=f"Cloned '{url}' into '{rel_path}'")

        # Every other operation needs an existing repo
        if not target.is_dir():
            return ToolResult(success=False, error=f"'{rel_path}' is not a directory")
        try:
            repo = Repo(target)
        except git.InvalidGitRepositoryError:
            return ToolResult(success=False, error=f"'{rel_path}' is not a git repository")

        if operation == "status":
            changed = [item.a_path for item in repo.index.diff(None)]
            staged = [item.a_path for item in repo.index.diff("HEAD")] if repo.head.is_valid() else []
            untracked = repo.untracked_files
            return ToolResult(success=True, output={
                "branch": repo.active_branch.name if not repo.head.is_detached else "(detached)",
                "changed": changed,
                "staged": staged,
                "untracked": untracked,
            })

        if operation == "log":
            if not repo.head.is_valid():
                return ToolResult(success=True, output=[])
            commits = list(repo.iter_commits(max_count=log_limit))
            return ToolResult(success=True, output=[
                {"hash": c.hexsha[:8], "message": c.message.strip(), "author": str(c.author), "date": c.committed_datetime.isoformat()}
                for c in commits
            ])

        if operation == "diff":
            return ToolResult(success=True, output=repo.git.diff())

        if operation == "add":
            if not files:
                return ToolResult(success=False, error="'files' is required for 'add'")
            repo.index.add(files)
            return ToolResult(success=True, output=f"Staged: {', '.join(files)}")

        if operation == "commit":
            if not message:
                return ToolResult(success=False, error="'message' is required for 'commit'")
            if not repo.index.diff("HEAD") and repo.head.is_valid():
                return ToolResult(success=False, error="Nothing staged to commit")
            commit = repo.index.commit(message)
            return ToolResult(success=True, output=f"Committed {commit.hexsha[:8]}: {message}")

        if operation == "branch":
            if not branch_name:
                return ToolResult(success=False, error="'branch_name' is required for 'branch'")
            new_branch = repo.create_head(branch_name)
            return ToolResult(success=True, output=f"Created branch '{new_branch.name}'")

        if operation == "checkout":
            if not branch_name:
                return ToolResult(success=False, error="'branch_name' is required for 'checkout'")
            try:
                repo.git.checkout(branch_name)
            except GitCommandError as e:
                return ToolResult(success=False, error=f"Checkout failed: {e}")
            return ToolResult(success=True, output=f"Checked out '{branch_name}'")

        return ToolResult(success=False, error=f"Unknown operation '{operation}'")
