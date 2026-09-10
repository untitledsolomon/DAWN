"""
GitHub webhook receiver — wakes DAWN up on GitHub events.

Subscribed events (per the GitHub integration spec):
  - issues (assigned to DAWN)          -> trigger an agent_tasks run
  - issue_comment (created)            -> respond if DAWN is @-mentioned
  - pull_request_review (submitted)     -> address changes_requested on DAWN PRs
  - pull_request_review_comment (created) -> respond to inline review comments
  - check_suite / check_run (failed)    -> post a Vercel-style failure comment

Loop prevention: events authored by DAWN's own bot identity are ignored, and
only OWNER/MEMBER/COLLABORATOR actors trigger autonomous action.
"""
import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Event types this receiver actually handles. Anything else returns a clean
# 200/no-op rather than erroring (a real-world bot failure mode).
HANDLED_EVENTS = {
    "issues", "issue_comment", "pull_request_review",
    "pull_request_review_comment", "check_suite", "check_run",
}

# Only these author associations may trigger autonomous action (avoids random
# external actors triggering DAWN on public repos).
TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def _verify_signature(payload_body: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Verify the X-Hub-Signature-256 header against the App webhook secret."""
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _bot_username() -> str:
    return getattr(settings, "github_bot_username", "") or ""


def _is_own_event(payload: dict) -> bool:
    """Whether the event was authored by DAWN's own bot identity (loop prevention)."""
    sender = payload.get("sender") or {}
    return sender.get("login") == _bot_username()


def _trusted(payload: dict) -> bool:
    """Whether the actor is a trusted association."""
    issue = payload.get("issue") or {}
    return issue.get("author_association") in TRUSTED_ASSOCIATIONS


async def _trigger_agent_task(goal: str, max_iterations: int = 50) -> None:
    """Create an agent_tasks row and run it through the agent loop, so
    webhook-triggered work is visible in the same Dashboard/activity feed as
    scheduled and manual runs."""
    import db.client as db
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("agent_tasks").insert({
        "goal": goal,
        "max_iterations": max_iterations,
        "status": "running",
        "progress": 0,
        "iterations": 0,
        "tools_used": [],
    }).execute())
    if not res.data:
        logger.error("[GitHubWebhook] Failed to create agent task row")
        return
    task_id = res.data[0]["id"]
    logger.info(f"[GitHubWebhook] Triggered agent task {task_id}: {goal[:80]}")

    # Run in the background so the webhook returns promptly.
    import asyncio
    asyncio.get_event_loop().create_task(_run_task(task_id, goal, max_iterations))


async def _run_task(task_id: str, goal: str, max_iterations: int) -> None:
    """Run an agent task to completion and record the outcome."""
    from llm.identity import resolve_identity, TrustTier
    from llm.agent import run_agent_loop
    import db.client as db
    supabase = db.get_db()

    key = getattr(settings, "dawn_api_key", None) or "dev-key"
    identity = resolve_identity(key)

    final_content = ""
    error = None
    try:
        async for event in run_agent_loop(user_message=goal, identity=identity, history=[], max_iterations=max_iterations):
            etype = event.get("type")
            if etype == "token":
                final_content = event.get("content", "")
            elif etype == "done":
                final_content = event.get("content", "")
            elif etype == "error":
                error = event.get("content", "Agent loop error")
            elif etype == "iteration_limit":
                error = event.get("content", "Iteration limit reached")
    except Exception as e:
        logger.exception(f"[GitHubWebhook] Agent task {task_id} failed")
        error = str(e)

    status = "completed" if not error else "failed"
    await db._async_execute(lambda: supabase.table("agent_tasks").update({
        "status": status,
        "progress": 100 if status == "completed" else 0,
    }).eq("id", task_id).execute())
    logger.info(f"[GitHubWebhook] Agent task {task_id} -> {status}")


async def _post_pr_comment(repo: str, pr_number: int, body: str, installation_id: int) -> None:
    """Post a comment on a PR (ungated — comments are never gated)."""
    try:
        from tools.github_client import get_github_client
        gh = get_github_client(installation_id)
        repo_obj = gh.get_repo(repo)
        pr = repo_obj.get_pull(pr_number)
        pr.create_issue_comment(body)
    except Exception as e:
        logger.error(f"[GitHubWebhook] Failed to post PR comment: {e}")


async def _handle_issue_assigned(payload: dict) -> None:
    issue = payload.get("issue") or {}
    repo = (payload.get("repository") or {}).get("full_name") or ""
    body = issue.get("body") or ""
    number = issue.get("number")
    title = issue.get("title") or ""
    goal = (
        f"GitHub issue #{number} ({title}) was assigned to you in {repo}.\n\n"
        f"Issue body:\n{body}\n\n"
        f"Work the issue, and open a PR against a dawn/* branch when done."
    )
    await _trigger_agent_task(goal)


async def _handle_issue_comment(payload: dict) -> None:
    # Only act if DAWN is @-mentioned, or if the comment is on an issue DAWN
    # is already working (best-effort: check for the bot username).
    comment = payload.get("comment") or {}
    body = comment.get("body") or ""
    if _bot_username() and _bot_username() not in body:
        return
    issue = payload.get("issue") or {}
    repo = (payload.get("repository") or {}).get("full_name") or ""
    goal = (
        f"GitHub comment in {repo} on issue #{issue.get('number')} mentions you:\n\n"
        f"{body}\n\nRespond appropriately."
    )
    await _trigger_agent_task(goal)


async def _handle_review(payload: dict) -> None:
    review = payload.get("review") or {}
    state = review.get("state")
    if state == "changes_requested":
        pr = payload.get("pull_request") or {}
        repo = (payload.get("repository") or {}).get("full_name") or ""
        body = review.get("body") or ""
        goal = (
            f"Changes were requested on PR #{pr.get('number')} in {repo}.\n\n"
            f"Review feedback:\n{body}\n\nAddress the feedback and update the PR."
        )
        await _trigger_agent_task(goal)


async def _handle_review_comment(payload: dict) -> None:
    comment = payload.get("comment") or {}
    body = comment.get("body") or ""
    if _bot_username() and _bot_username() not in body:
        return
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name") or ""
    goal = (
        f"Inline review comment on PR #{pr.get('number')} in {repo} mentions you:\n\n"
        f"{body}\n\nRespond appropriately."
    )
    await _trigger_agent_task(goal)


async def _handle_check_failure(payload: dict) -> None:
    # Vercel/PostHog-style: post a comment on the PR summarizing the CI failure.
    pr = payload.get("pull_request") or {}
    repo = (payload.get("repository") or {}).get("full_name") or ""
    pr_number = pr.get("number")
    installation_id = (payload.get("installation") or {}).get("id")
    if not pr_number or not installation_id:
        return
    check_name = (payload.get("check_run") or {}).get("name") or "CI"
    details_url = (payload.get("check_run") or {}).get("details_url") or ""
    summary = (payload.get("check_run") or {}).get("output", {}).get("summary") or ""
    body = (
        f"Check '{check_name}' failed on this PR.\n\n"
        f"{summary}\n\n"
        f"[View details]({details_url})"
    )
    await _post_pr_comment(repo, pr_number, body, installation_id)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    x_github_event: Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """Receive a GitHub webhook event and act on it."""
    secret = getattr(settings, "github_webhook_secret", None)
    if not secret:
        logger.warning("[GitHubWebhook] No github_webhook_secret configured — ignoring webhook")
        return {"status": "ignored", "reason": "webhook_secret_not_configured"}

    payload_body = await request.body()
    if not _verify_signature(payload_body, x_hub_signature_256, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(payload_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Loop prevention: never react to our own events.
    if _is_own_event(payload):
        return {"status": "ignored", "reason": "own_event"}

    event = x_github_event or ""
    action = payload.get("action", "")

    if event not in HANDLED_EVENTS:
        return {"status": "ignored", "reason": f"unhandled_event:{event}"}

    logger.info(f"[GitHubWebhook] event={event} action={action}")

    # Trust check: only OWNER/MEMBER/COLLABORATOR actors trigger autonomous work.
    if not _trusted(payload):
        return {"status": "ignored", "reason": "untrusted_actor"}

    try:
        if event == "issues" and action == "assigned":
            await _handle_issue_assigned(payload)
        elif event == "issue_comment" and action == "created":
            await _handle_issue_comment(payload)
        elif event == "pull_request_review" and action == "submitted":
            await _handle_review(payload)
        elif event == "pull_request_review_comment" and action == "created":
            await _handle_review_comment(payload)
        elif event in ("check_suite", "check_run"):
            conclusion = (payload.get("check_run") or {}).get("conclusion") or \
                         (payload.get("check_suite") or {}).get("conclusion")
            if conclusion == "failure":
                await _handle_check_failure(payload)
    except Exception as e:
        logger.exception(f"[GitHubWebhook] Failed to handle {event}")
        return {"status": "error", "detail": str(e)}

    return {"status": "ok"}
