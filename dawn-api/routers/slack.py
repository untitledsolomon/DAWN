"""
Slack Integration Router — manages Slack bot lifecycle and provides
API endpoints for Slack-related operations.

This router:
1. Starts/stops the Slack Socket Mode bot as a background service
2. Provides endpoints for Slack app configuration
3. Exposes Slack message sending for other parts of DAWN
"""

import os
import json
import logging
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slack", tags=["slack"])

# ── Global reference to the Slack bot thread ────────────────────────────
_slack_thread: Optional[threading.Thread] = None
_slack_running = False


# ── Schemas ─────────────────────────────────────────────────────────────

class SlackMessageRequest(BaseModel):
    channel: str
    text: str
    thread_ts: Optional[str] = None


class SlackStatusResponse(BaseModel):
    running: bool
    configured: bool
    bot_token_set: bool
    app_token_set: bool


# ── Auth ────────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    from config import settings
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Bot Lifecycle ───────────────────────────────────────────────────────

def _start_bot_thread():
    """Start the Slack Socket Mode bot in a daemon thread."""
    global _slack_running
    try:
        from slack_bot.app import start_slack_bot
        _slack_running = True
        start_slack_bot()
    except Exception as e:
        logger.error(f"Slack bot thread failed: {e}")
        _slack_running = False


@router.post("/start", response_model=SlackStatusResponse)
async def start_slack_bot(_=Depends(verify_key)):
    """Start the Slack Socket Mode bot."""
    global _slack_thread, _slack_running

    if _slack_running:
        return SlackStatusResponse(
            running=True,
            configured=True,
            bot_token_set=bool(os.environ.get("SLACK_BOT_TOKEN")),
            app_token_set=bool(os.environ.get("SLACK_APP_TOKEN")),
        )

    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")

    if not bot_token or not app_token:
        raise HTTPException(
            status_code=400,
            detail="SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set in environment"
        )

    _slack_thread = threading.Thread(target=_start_bot_thread, daemon=True)
    _slack_thread.start()

    logger.info("Slack bot starting in background thread...")
    return SlackStatusResponse(
        running=True,
        configured=True,
        bot_token_set=True,
        app_token_set=True,
    )


@router.post("/stop")
async def stop_slack_bot(_=Depends(verify_key)):
    """Signal the Slack bot to stop (thread will terminate on next iteration)."""
    global _slack_running
    _slack_running = False
    return {"status": "stopped"}


@router.get("/status", response_model=SlackStatusResponse)
async def slack_status():
    """Check if the Slack bot is running."""
    return SlackStatusResponse(
        running=_slack_running,
        configured=True,
        bot_token_set=bool(os.environ.get("SLACK_BOT_TOKEN")),
        app_token_set=bool(os.environ.get("SLACK_APP_TOKEN")),
    )


# ── Message Sending ─────────────────────────────────────────────────────

@router.post("/send")
async def send_slack_message(req: SlackMessageRequest, _=Depends(verify_key)):
    """
    Send a message to a Slack channel.
    Used by other parts of DAWN (e.g., agent tasks, monitoring alerts).
    """
    try:
        from slack_sdk import WebClient
        client = WebClient(token=os.environ.get("SLACK_BOT_TOKEN", ""))
        
        kwargs = {"channel": req.channel, "text": req.text}
        if req.thread_ts:
            kwargs["thread_ts"] = req.thread_ts

        response = client.chat_postMessage(**kwargs)
        return {"ok": True, "ts": response.get("ts"), "channel": req.channel}
    except Exception as e:
        logger.error(f"Failed to send Slack message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Manifest / Setup Info ───────────────────────────────────────────────

@router.get("/setup")
async def slack_setup_info():
    """Return instructions for setting up the Slack app."""
    return {
        "instructions": [
            "1. Go to https://api.slack.com/apps",
            "2. Click 'Create New App' → 'From Manifest'",
            "3. Copy the contents of slack_bot/manifest.yaml and paste",
            "4. After creation, go to 'Socket Mode' and enable it",
            "5. Go to 'OAuth & Permissions' → 'Install to Workspace'",
            "6. Copy the Bot Token (starts with xoxb-)",
            "7. Go to 'Basic Information' → 'App-Level Tokens' → 'Generate Token'",
            "   Name: 'dawn-socket', Scope: 'connections:write'",
            "8. Copy the App Token (starts with xapp-)",
            "9. Set these as environment variables:",
            "   SLACK_BOT_TOKEN=xoxb-...",
            "   SLACK_APP_TOKEN=xapp-...",
            "   SLACK_SIGNING_SECRET=... (from Basic Information)",
            "10. Call POST /slack/start to launch the bot",
        ],
        "manifest_path": "slack_bot/manifest.yaml",
    }
