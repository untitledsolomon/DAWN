"""
GitHub API client — authenticates as a GitHub App and returns a PyGithub
client for a specific installation (org/repo DAWN has been installed into).

Using a GitHub App (not a PAT) gives DAWN its own identity (`dawn-bot`),
scoped permissions, and built-in webhook delivery — so DAWN's commits,
comments, and reviews are distinguishable from Solomon's own, and the audit
trail for autonomous actions is clean.
"""
import logging
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def github_configured() -> bool:
    """Whether GitHub App credentials are present in config."""
    return bool(getattr(settings, "github_app_id", None)
                and getattr(settings, "github_app_private_key", None))


def get_github_client(installation_id: int):
    """Return an authenticated PyGithub client for a specific App installation.

    Raises RuntimeError if GitHub App credentials aren't configured.
    """
    if not github_configured():
        raise RuntimeError("GitHub App credentials not configured (GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY)")
    try:
        from github import GithubIntegration, Github
        integration = GithubIntegration(
            str(settings.github_app_id),
            settings.github_app_private_key,
        )
        access_token = integration.get_access_token(installation_id).token
        return Github(access_token)
    except Exception as e:
        logger.error(f"Failed to authenticate GitHub App: {e}")
        raise RuntimeError(f"GitHub App authentication failed: {e}")
