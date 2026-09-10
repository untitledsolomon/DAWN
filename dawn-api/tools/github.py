"""
GitHub integration tool — push, PRs, issues, reviews.

Separate from tools/git.py (which stays the local-sandbox-only tool for
clone/status/log/diff/add/commit/branch/checkout). This tool talks to the
GitHub API via a GitHub App.

Approval model (mirrors GitHub Copilot Coding Agent, the explicit reference):
  - Comments and pushes to `dawn/*` branches are NEVER gated — they're cheap
    and reversible, and a bad push is isolated on a branch DAWN owns.
  - The two real controls are structural, not per-call:
      1. DAWN can never approve/merge its own PR (review_pr rejects
         APPROVE/REQUEST_CHANGES on DAWN-authored PRs; merge requires a human
         via branch protection).
      2. Actions triggered by DAWN's push require manual "Approve and run"
         (a GitHub-native repo/org setting).
  So this tool does NOT route through the pending_actions queue.
"""
import logging
from typing import Optional

from tools.base import BaseTool, ToolResult
from tools.github_client import github_configured, get_github_client
from config import settings

logger = logging.getLogger(__name__)

DAWN_BRANCH_PREFIX = "dawn/"

OPERATIONS = [
    "push", "create_pr", "list_prs", "get_pr", "comment_on_pr", "review_pr",
    "list_issues", "get_issue", "comment_on_issue", "list_pr_comments",
    "get_pr_checks",
]


class GitHubTool(BaseTool):
    name = "github"
    description = (
        "Interact with GitHub: push branches, open/read/comment on pull "
        "requests, read/comment on issues, and submit PR reviews. DAWN can "
        "only push to branches prefixed 'dawn/'. Comments and dawn/* pushes "
        "run immediately; DAWN can never approve or merge its own PRs."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": OPERATIONS,
                "description": "The GitHub operation to perform.",
            },
            "repo": {
                "type": "string",
                "description": "owner/repo, e.g. 'untitledsolomon/DAWN'.",
            },
            "installation_id": {
                "type": "integer",
                "description": "GitHub App installation id for the org/repo. "
                               "Resolved automatically from the webhook when "
                               "available; provide explicitly otherwise.",
            },
            "branch": {"type": "string", "description": "For 'push'/'create_pr': the branch to push/use."},
            "base": {"type": "string", "description": "For 'create_pr': the base branch (default 'main')."},
            "head": {"type": "string", "description": "For 'create_pr': the head branch."},
            "title": {"type": "string", "description": "For 'create_pr': PR title."},
            "body": {"type": "string", "description": "For 'create_pr'/'comment_*': body text."},
            "pr_number": {"type": "integer", "description": "For PR operations: the PR number."},
            "issue_number": {"type": "integer", "description": "For issue operations: the issue number."},
            "review_event": {
                "type": "string",
                "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                "description": "For 'review_pr': the review event type.",
            },
        },
        "required": ["operation", "repo"],
    }

    async def run(self, operation: str, repo: str, **kwargs) -> ToolResult:
        if operation not in OPERATIONS:
            return ToolResult(success=False, error=f"Unknown operation '{operation}'")
        if not github_configured():
            return ToolResult(
                success=False,
                error="GitHub App not configured (GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY).",
            )

        installation_id = kwargs.get("installation_id")
        if not installation_id:
            return ToolResult(success=False, error="installation_id is required for GitHub operations.")

        try:
            gh = get_github_client(int(installation_id))
        except RuntimeError as e:
            return ToolResult(success=False, error=str(e))

        try:
            if operation == "push":
                return await self._push(gh, repo, kwargs)
            if operation == "create_pr":
                return await self._create_pr(gh, repo, kwargs)
            if operation == "list_prs":
                return await self._list_prs(gh, repo)
            if operation == "get_pr":
                return await self._get_pr(gh, repo, kwargs)
            if operation == "comment_on_pr":
                return await self._comment_on_pr(gh, repo, kwargs)
            if operation == "review_pr":
                return await self._review_pr(gh, repo, kwargs)
            if operation == "list_issues":
                return await self._list_issues(gh, repo)
            if operation == "get_issue":
                return await self._get_issue(gh, repo, kwargs)
            if operation == "comment_on_issue":
                return await self._comment_on_issue(gh, repo, kwargs)
            if operation == "list_pr_comments":
                return await self._list_pr_comments(gh, repo, kwargs)
            if operation == "get_pr_checks":
                return await self._get_pr_checks(gh, repo, kwargs)
        except Exception as e:
            logger.exception(f"GitHub operation '{operation}' failed")
            return ToolResult(success=False, error=f"GitHub operation '{operation}' failed: {e}")

        return ToolResult(success=False, error=f"Unknown operation '{operation}'")

    # ── Push ────────────────────────────────────────────────────────────────

    async def _push(self, gh, repo: str, kwargs: dict) -> ToolResult:
        branch = kwargs.get("branch")
        if not branch:
            return ToolResult(success=False, error="'branch' is required for push.")
        if not branch.startswith(DAWN_BRANCH_PREFIX):
            return ToolResult(
                success=False,
                error=f"DAWN can only push to branches prefixed '{DAWN_BRANCH_PREFIX}' — got '{branch}'.",
            )
        # The local repo must already have the branch committed (via tools/git.py).
        # This tool pushes the current local branch state to the remote.
        # (Full push implementation requires a local clone; see tools/git.py.)
        return ToolResult(
            success=False,
            error=(
                "Push requires a local clone of the repo (use tools/git.py to "
                "clone and commit first). Pushing from a remote-only context "
                "is not supported yet."
            ),
        )

    # ── PRs ────────────────────────────────────────────────────────────────

    async def _create_pr(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.create_pull(
            title=kwargs.get("title") or "DAWN changes",
            body=kwargs.get("body") or "",
            head=kwargs.get("head") or kwargs.get("branch") or "",
            base=kwargs.get("base") or "main",
        )
        return ToolResult(success=True, output={
            "number": pr.number, "url": pr.html_url, "title": pr.title, "state": pr.state,
        })

    async def _list_prs(self, gh, repo: str) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        prs = repo_obj.get_pulls(state="open")
        return ToolResult(success=True, output=[
            {"number": p.number, "title": p.title, "state": p.state, "url": p.html_url,
             "user": p.user.login if p.user else None}
            for p in prs
        ])

    async def _get_pr(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(int(kwargs["pr_number"]))
        return ToolResult(success=True, output={
            "number": pr.number, "title": pr.title, "state": pr.state, "body": pr.body,
            "user": pr.user.login if pr.user else None, "url": pr.html_url,
            "mergeable": pr.mergeable, "head": pr.head.ref, "base": pr.base.ref,
        })

    async def _comment_on_pr(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(int(kwargs["pr_number"]))
        comment = pr.create_issue_comment(kwargs.get("body") or "")
        return ToolResult(success=True, output={"id": comment.id, "url": comment.html_url})

    async def _review_pr(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(int(kwargs["pr_number"]))
        event = kwargs.get("review_event") or "COMMENT"
        # No self-approval: DAWN can never Approve/Request-changes its own PR.
        author = pr.user.login if pr.user else None
        bot = getattr(settings, "github_bot_username", None)
        if bot and author == bot and event in ("APPROVE", "REQUEST_CHANGES"):
            return ToolResult(
                success=False,
                error="DAWN cannot approve or request changes on its own PR — only COMMENT-type reviews are allowed.",
            )
        review = pr.create_review(event=event, body=kwargs.get("body") or "")
        return ToolResult(success=True, output={"id": review.id, "state": event, "url": review.html_url})

    async def _list_pr_comments(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(int(kwargs["pr_number"]))
        comments = pr.get_issue_comments()
        return ToolResult(success=True, output=[
            {"id": c.id, "user": c.user.login if c.user else None, "body": c.body, "created_at": str(c.created_at)}
            for c in comments
        ])

    async def _get_pr_checks(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(int(kwargs["pr_number"]))
        checks = pr.get_commits()[0].get_check_runs()
        return ToolResult(success=True, output=[
            {"name": c.name, "status": c.status, "conclusion": c.conclusion,
             "details_url": c.details_url}
            for c in checks
        ])

    # ── Issues ──────────────────────────────────────────────────────────────

    async def _list_issues(self, gh, repo: str) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        issues = repo_obj.get_issues(state="open")
        return ToolResult(success=True, output=[
            {"number": i.number, "title": i.title, "state": i.state, "url": i.html_url,
             "user": i.user.login if i.user else None}
            for i in issues
        ])

    async def _get_issue(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        issue = repo_obj.get_issue(int(kwargs["issue_number"]))
        return ToolResult(success=True, output={
            "number": issue.number, "title": issue.title, "state": issue.state,
            "body": issue.body, "user": issue.user.login if issue.user else None,
            "url": issue.html_url,
        })

    async def _comment_on_issue(self, gh, repo: str, kwargs: dict) -> ToolResult:
        repo_obj = gh.get_repo(repo)
        issue = repo_obj.get_issue(int(kwargs["issue_number"]))
        comment = issue.create_comment(kwargs.get("body") or "")
        return ToolResult(success=True, output={"id": comment.id, "url": comment.html_url})
