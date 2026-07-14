"""
Slack Bolt App — Socket Mode, no public endpoint needed.
Runs as a background process alongside the DAWN API.

Architecture:
  Slack (Socket Mode) → SlackBoltApp → DAWN API (HTTP) → LLM + DB

The Bolt app is lazily initialized — it only connects to Slack when
start_slack_bot() is called, not on module import. This lets the
module be imported without Slack tokens being set.

Session UUID Mapping:
  Slack channel IDs (e.g. "D0BH78FJ8LU") are NOT valid UUIDs.
  This bot maintains a {slack_channel_id: dawn_uuid} mapping that
  persists to .session_map.json so conversations survive restarts.
"""

import os
import json
import logging
import asyncio
import uuid
import httpx
from typing import Optional

from slack_bolt import Ack
from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
DAWN_API_URL = os.environ.get("DAWN_API_URL", "http://localhost:8000")
DAWN_API_KEY = os.environ.get("DAWN_API_KEY", "dev-key")

SESSION_MAP_PATH = os.environ.get(
    "SLACK_SESSION_MAP_PATH",
    os.path.join(os.path.dirname(__file__), ".session_map.json")
)

# Lazy-initialized app — None until start_slack_bot() is called
_app = None


# ── Session UUID Mapping ────────────────────────────────────────────────────

def _load_session_map() -> dict:
    """Load the {slack_channel_id: dawn_uuid} mapping from disk."""
    if os.path.exists(SESSION_MAP_PATH):
        try:
            with open(SESSION_MAP_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load session map: {e}")
    return {}


def _save_session_map(mapping: dict):
    """Persist the session mapping to disk."""
    try:
        os.makedirs(os.path.dirname(SESSION_MAP_PATH) or ".", exist_ok=True)
        with open(SESSION_MAP_PATH, "w") as f:
            json.dump(mapping, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to save session map: {e}")


def get_or_create_session_id(slack_channel_id: str) -> str:
    """
    Return a DAWN-compatible UUID session_id for a Slack channel.
    Creates and persists a new UUID if this channel hasn't been seen before.
    """
    mapping = _load_session_map()
    if slack_channel_id in mapping:
        return mapping[slack_channel_id]

    new_uuid = str(uuid.uuid4())
    mapping[slack_channel_id] = new_uuid
    _save_session_map(mapping)
    logger.info(f"Mapped Slack channel {slack_channel_id} → DAWN session {new_uuid}")
    return new_uuid


# ── App Factory ─────────────────────────────────────────────────────────────

def get_app():
    """Get or create the Bolt App instance (lazy initialization)."""
    global _app
    if _app is None:
        from slack_bolt import App
        _app = App(
            token=SLACK_BOT_TOKEN,
            signing_secret=SLACK_SIGNING_SECRET,
        )
        _register_handlers(_app)
    return _app


# ── Helpers ─────────────────────────────────────────────────────────────────

async def query_dawn(
    message: str,
    session_id: Optional[str] = None,
) -> str:
    """
    Send a message to DAWN's chat endpoint and get the response text.

    session_id should be a valid UUID (from get_or_create_session_id) or None
    (the API will create one). Never pass a Slack channel ID directly.
    """
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "message": message,
                "session_id": session_id,  # None is fine — API creates one
                "web_search_enabled": False,
            }
            resp = await client.post(
                f"{DAWN_API_URL}/chat/",
                json=payload,
                headers={
                    "x-api-key": DAWN_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(f"DAWN API error: {resp.status_code} {resp.text[:200]}")
                return f"⚠️ DAWN API returned {resp.status_code}. Check logs."

            # Parse SSE stream — collect all tokens
            full_text = ""
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "token":
                            full_text += data.get("content", "")
                        elif data.get("type") == "done":
                            break
                    except json.JSONDecodeError:
                        continue

            return full_text.strip() or "🤖 DAWN processed your message but returned no text."

    except httpx.RequestError as e:
        logger.error(f"DAWN API connection failed: {e}")
        return f"⚠️ Could not reach DAWN API: {e}"
    except Exception as e:
        logger.error(f"Unexpected error querying DAWN: {e}")
        return f"⚠️ Unexpected error: {e}"


# ── Handler Registration ────────────────────────────────────────────────────

def _register_handlers(app):
    """Register all event handlers and slash commands on the Bolt app."""

    @app.event("app_mention")
    def handle_mention(event: dict, say, client: WebClient):
        """When someone @DAWN in a channel."""
        try:
            text = event.get("text", "")
            import re
            text = re.sub(r"<@\w+>", "", text).strip()

            if not text:
                say("👋 Hi! What can I help you with?")
                return

            channel = event.get("channel", "")
            session_id = get_or_create_session_id(channel)

            response = asyncio.run(query_dawn(text, session_id=session_id))
            say(response)

        except Exception as e:
            logger.error(f"Error in handle_mention: {e}", exc_info=True)
            say(f"⚠️ Sorry, I hit an error: {str(e)[:200]}")

    @app.event("message")
    def handle_dm(event: dict, say, client: WebClient):
        """Handle direct messages to DAWN."""
        try:
            channel_type = event.get("channel_type", "")
            if channel_type != "im":
                return

            text = event.get("text", "").strip()
            if not text:
                return

            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return

            channel = event.get("channel", "")
            session_id = get_or_create_session_id(channel)

            response = asyncio.run(query_dawn(text, session_id=session_id))
            say(response)

        except Exception as e:
            logger.error(f"Error in handle_dm: {e}", exc_info=True)

    @app.command("/dawn")
    def handle_dawn_command(ack: Ack, command: dict, say):
        """Generic /dawn command."""
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/dawn <your question or command>`")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn(text, session_id=session_id))
        say(response)

    @app.command("/status")
    def handle_status(ack: Ack, say):
        """Quick system status check."""
        ack()
        try:
            # Use a dedicated session for status checks so they don't pollute
            # the user's conversation history
            session_id = get_or_create_session_id("_system_status")
            resp = asyncio.run(query_dawn(
                "Run a quick system health check and return the status.",
                session_id=session_id,
            ))
            say(f"📊 *DAWN System Status*\n{resp}")
        except Exception as e:
            say(f"⚠️ Status check failed: {e}")

    @app.command("/revenue")
    def handle_revenue(ack: Ack, say):
        """Quick revenue summary."""
        ack()
        try:
            session_id = get_or_create_session_id("_system_revenue")
            resp = asyncio.run(query_dawn(
                "What's the current revenue situation? Summarize active clients, "
                "monthly recurring revenue, and any overdue invoices.",
                session_id=session_id,
            ))
            say(f"💰 *Revenue Summary*\n{resp}")
        except Exception as e:
            say(f"⚠️ Revenue check failed: {e}")

    # ── Channel Monitoring ──────────────────────────────────────────────────

    @app.event("message")
    def handle_channel_messages(event: dict, client: WebClient):
        """Passive monitoring of #sales, #support, #ops, #billing, #general."""
        try:
            channel = event.get("channel", "")
            text = event.get("text", "").strip()
            user = event.get("user", "")
            channel_type = event.get("channel_type", "")

            if channel_type not in ("channel", "group"):
                return
            if event.get("bot_id") or event.get("subtype") == "bot_message":
                return

            try:
                info = client.conversations_info(channel=channel)
                channel_name = info.get("channel", {}).get("name", "")
            except Exception:
                channel_name = ""

            if channel_name not in ("sales", "support", "ops", "billing", "general"):
                return

            logger.info(f"[channel_monitor] #{channel_name} — {user}: {text[:100]}")

        except Exception as e:
            logger.error(f"Error in channel monitoring: {e}")


# ── Startup ─────────────────────────────────────────────────────────────────

def start_slack_bot():
    """Start the Slack bot in Socket Mode. Call this from a background thread."""
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        logger.error(
            "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set. "
            "Create a Slack app at https://api.slack.com/apps"
        )
        return

    logger.info("Starting Slack bot in Socket Mode...")
    app = get_app()
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_slack_bot()
