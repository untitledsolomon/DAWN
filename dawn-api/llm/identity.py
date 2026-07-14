"""
Identity and trust tiers for DAWN.

This is deliberately narrow: it answers "who is this request authenticated
as" and "what tier of tool access does that identity get." It does NOT
grant blanket trust that bypasses the harm/consequence checks in
llm/safety.py — see that module's docstring for why. A request from the
owner tier still goes through the same "could this cause real harm"
reasoning as any other; it additionally unlocks tools that other
tiers can't call at all (e.g. install_skill, git push once that lands).

Multiple API keys, not one shared dawn_api_key. Configure via
DAWN_API_KEYS in .env as a JSON object, e.g.:
  DAWN_API_KEYS={"sk-owner-xxx": "owner", "sk-app-yyy": "service"}

Falls back to treating settings.dawn_api_key (the old single-key field) as
an "owner" key if DAWN_API_KEYS isn't set, so existing deployments don't
break on upgrade — but you should migrate off the shared key.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional
import json
import logging
from config import settings

logger = logging.getLogger(__name__)


class TrustTier(str, Enum):
    OWNER = "owner"       # Solomon — full tool access, still subject to safety checks
    SERVICE = "service"    # other Regent apps/services — restricted tool set
    UNKNOWN = "unknown"     # unrecognised key — should never reach here if auth is enforced upstream


# Tools each tier may call. Tools not listed for a tier are invisible to it —
# the registry filters specs per-request, so a restricted identity's LLM call
# doesn't even see install_skill/git as options, rather than seeing them and
# being refused after the fact.
#
# v37.0: Expanded SERVICE tier to include delegation, Axis, Forge, and email tools.
TIER_TOOL_ACCESS: dict[TrustTier, set[str] | None] = {
    TrustTier.OWNER: None,  # None = all registered tools
    TrustTier.SERVICE: {
        "filesystem", "web_search", "knowledge_graph", "create_chart",
        "delegate_to_subagent", "delegate_parallel",
        "axis_payroll", "axis_tax", "axis_employees",
        "forge_pages", "forge_blog", "forge_analytics",
        "send_email", "email_status",
        "web_fetch", "terminal",
    },
    TrustTier.UNKNOWN: set(),
}


@dataclass
class Identity:
    key_id: str
    tier: TrustTier

    def allowed_tools(self, all_tool_names: list[str]) -> list[str]:
        allowed = TIER_TOOL_ACCESS.get(self.tier, set())
        if allowed is None:
            return all_tool_names
        return [n for n in all_tool_names if n in allowed]


def _load_key_map() -> dict[str, str]:
    raw = getattr(settings, "dawn_api_keys", None)
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("DAWN_API_KEYS is set but not valid JSON — ignoring it")

    # Fallback: old single shared key, treated as owner-tier
    legacy_key = getattr(settings, "dawn_api_key", None)
    if legacy_key:
        return {legacy_key: "owner"}
    return {}


def resolve_identity(api_key: Optional[str]) -> Identity:
    """
    Maps a raw API key to an Identity. Callers (routers) should treat a
    result of tier=UNKNOWN as unauthenticated and reject the request —
    this function itself doesn't raise, it's the router's job to enforce
    the 401, matching the existing verify_key() pattern in chat.py/agent.py.
    """
    if not api_key:
        return Identity(key_id="", tier=TrustTier.UNKNOWN)

    key_map = _load_key_map()
    tier_str = key_map.get(api_key)

    if tier_str is None:
        return Identity(key_id=api_key, tier=TrustTier.UNKNOWN)

    try:
        tier = TrustTier(tier_str)
    except ValueError:
        logger.warning(f"DAWN_API_KEYS has unknown tier '{tier_str}' — treating as UNKNOWN")
        tier = TrustTier.UNKNOWN

    return Identity(key_id=api_key[:8] + "...", tier=tier)
