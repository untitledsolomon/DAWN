"""
Proactive Agents — scheduled tasks that push notifications to Slack.

These agents run on schedules (hourly, daily, weekly) and send
proactive messages to designated Slack channels without being asked.

Architecture:
  scheduler (APScheduler) → agent function → Slack WebClient → channel

Agents:
  1. Lead Scanner    — every 6h: "3 new leads from LinkedIn"
  2. Pipeline Monitor — daily: "2 leads going cold"
  3. Campaign Reporter — on campaign complete: "Campaign done: 45% reply rate"
  4. Revenue Tracker   — weekly: "MTD: $8,200 vs $15k target"
  5. System Health     — daily: "VPS disk at 85%"

Each agent logs its runs to the agent_tasks table.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
DAWN_API_URL = os.environ.get("DAWN_API_URL", "http://localhost:8000")
DAWN_API_KEY = os.environ.get("DAWN_API_KEY", "dev-key")

# Default channels for agent notifications
AGENT_CHANNELS = {
    "leads": os.environ.get("AGENT_CHANNEL_LEADS", "sales"),
    "pipeline": os.environ.get("AGENT_CHANNEL_PIPELINE", "sales"),
    "campaigns": os.environ.get("AGENT_CHANNEL_CAMPAIGNS", "marketing"),
    "revenue": os.environ.get("AGENT_CHANNEL_REVENUE", "general"),
    "system": os.environ.get("AGENT_CHANNEL_SYSTEM", "ops"),
    "alerts": os.environ.get("AGENT_CHANNEL_ALERTS", "ops"),
}

# ── Helpers ─────────────────────────────────────────────────────────────

def _slack_client() -> Optional[WebClient]:
    """Get a Slack WebClient if token is configured."""
    if not SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not set, cannot send Slack messages")
        return None
    return WebClient(token=SLACK_BOT_TOKEN)


async def _crm_api_get(path: str) -> dict:
    """Call DAWN's internal CRM agent endpoint."""
    url = f"{DAWN_API_URL}/crm{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            url,
            headers={
                "x-api-key": DAWN_API_KEY,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.error(f"CRM API GET {path} failed: {resp.status_code}")
            return {}
        return resp.json()


def _send_slack_message(channel: str, text: str, blocks: Optional[list] = None):
    """Send a message to a Slack channel."""
    client = _slack_client()
    if not client:
        return

    try:
        kwargs = {"channel": channel, "text": text}
        if blocks:
            kwargs["blocks"] = blocks
        client.chat_postMessage(**kwargs)
        logger.info(f"Sent message to #{channel}")
    except Exception as e:
        logger.error(f"Failed to send Slack message to #{channel}: {e}")


# ── Agent Functions ────────────────────────────────────────────────────

async def scan_new_leads():
    """
    Lead Scanner Agent — runs every 6 hours.
    Checks for new leads since last run and reports highlights.
    """
    logger.info("[Lead Scanner] Checking for new leads...")

    try:
        data = await _crm_api_get("/leads/summary")
        if not data or "error" in data:
            logger.warning(f"[Lead Scanner] No data: {data}")
            return

        total = data.get("total_leads", 0)
        new_count = data.get("new_leads", 0)
        sources = data.get("leads_by_source", {})

        if new_count == 0:
            logger.info("[Lead Scanner] No new leads since last check.")
            return

        # Build message
        source_text = ""
        if sources:
            top_sources = sorted(sources.items(), key=lambda x: -x[1])[:3]
            source_text = "\n".join([f"  • *{s}*: {c}" for s, c in top_sources])

        recent = data.get("recent_leads", [])
        recent_text = ""
        if recent:
            recent_text = "\n".join([
                f"  • {r.get('name', '')} — {r.get('business', '')} ({r.get('source', 'unknown')})"
                for r in recent[:3]
            ])

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔍 New Leads Found", "emoji": True},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{new_count}* new leads in the pipeline (out of {total} total).",
                },
            },
        ]

        if source_text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Top Sources:*\n{source_text}"},
            })

        if recent_text:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Latest:*\n{recent_text}"},
            })

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}],
        })

        _send_slack_message(AGENT_CHANNELS["leads"], f"{new_count} new leads found", blocks)
        logger.info(f"[Lead Scanner] Reported {new_count} new leads.")

    except Exception as e:
        logger.error(f"[Lead Scanner] Error: {e}")


async def monitor_pipeline():
    """
    Pipeline Monitor Agent — runs daily.
    Checks for leads going cold (no contact in 7+ days) and pipeline health.
    """
    logger.info("[Pipeline Monitor] Checking pipeline health...")

    try:
        data = await _crm_api_get("/leads/summary")
        if not data:
            return

        new_count = data.get("new_leads", 0)
        contacted = data.get("contacted", 0)
        follow_up = data.get("follow_up", 0)
        interested = data.get("interested", 0)
        closed = data.get("closed", 0)
        total = data.get("total_leads", 0)
        conversion = data.get("conversion_rate", 0)

        # Get stale leads (new but not contacted)
        stale_count = new_count  # Simplification: all "new" leads need attention

        if stale_count == 0 and conversion >= 10:
            logger.info("[Pipeline Monitor] Pipeline healthy.")
            return

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 Pipeline Health Check", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"🆕 *New:* {new_count}"},
                    {"type": "mrkdwn", "text": f"🔵 *Contacted:* {contacted}"},
                    {"type": "mrkdwn", "text": f"🟡 *Follow-up:* {follow_up}"},
                    {"type": "mrkdwn", "text": f"🟠 *Interested:* {interested}"},
                    {"type": "mrkdwn", "text": f"🟢 *Closed:* {closed}"},
                    {"type": "mrkdwn", "text": f"📈 *Conversion:* {conversion}%"},
                ],
            },
        ]

        if stale_count > 0:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *{stale_count} leads* need attention — not yet contacted.",
                },
            })

        if conversion < 5 and total > 20:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📉 *Conversion rate is low* ({conversion}%). Consider reviewing your outreach sequence.",
                },
            })

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}],
        })

        _send_slack_message(AGENT_CHANNELS["pipeline"], "Pipeline health check", blocks)
        logger.info("[Pipeline Monitor] Report sent.")

    except Exception as e:
        logger.error(f"[Pipeline Monitor] Error: {e}")


async def check_system_health():
    """
    System Health Agent — runs daily.
    Checks VPS disk, RAM, CPU, and DAWN API health.
    """
    logger.info("[System Health] Checking system status...")

    try:
        # Check DAWN API health
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{DAWN_API_URL}/health")
            health = resp.json() if resp.status_code == 200 else {"status": "error"}
    except Exception as e:
        health = {"status": "unreachable", "error": str(e)}

    # Check disk space (if running on the VPS)
    disk_usage = "unknown"
    try:
        import shutil
        usage = shutil.disk_usage("/")
        percent = (usage.used / usage.total) * 100
        disk_usage = f"{percent:.1f}%"
    except Exception:
        pass

    status_emoji = "🟢" if health.get("status") == "ok" else "🔴"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{status_emoji} System Health Report", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*API Status:* {health.get('status', 'unknown')}"},
                {"type": "mrkdwn", "text": f"*Version:* {health.get('version', '?')}"},
                {"type": "mrkdwn", "text": f"*Disk:* {disk_usage}"},
                {"type": "mrkdwn", "text": f"*LLM Mode:* {health.get('llm_mode', '?')}"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}],
        },
    ]

    _send_slack_message(AGENT_CHANNELS["system"], "System health report", blocks)
    logger.info("[System Health] Report sent.")


async def track_revenue():
    """
    Revenue Tracker Agent — runs weekly.
    Reports MTD revenue, active deals, and targets.
    """
    logger.info("[Revenue Tracker] Checking revenue...")

    try:
        # Query deals from DAWN's own Supabase
        supabase_url = os.environ.get("SUPABASE_URL", "")
        supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")

        if not supabase_url or not supabase_key:
            logger.warning("[Revenue Tracker] Supabase not configured")
            return

        headers = {
            "Authorization": f"Bearer {supabase_key}",
            "apikey": supabase_key,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get won deals this month
            now = datetime.now(timezone.utc)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            resp = await client.get(
                f"{supabase_url}/rest/v1/deals",
                headers=headers,
                params={
                    "status": "eq.won",
                    "close_date": f"gte.{month_start.isoformat()}",
                    "select": "value,currency,name,client_name,close_date",
                },
            )

            if resp.status_code == 200:
                deals = resp.json()
                total_revenue = sum(d.get("value", 0) for d in deals)
                deal_count = len(deals)
            else:
                deals = []
                total_revenue = 0
                deal_count = 0

            # Get pending deals
            resp2 = await client.get(
                f"{supabase_url}/rest/v1/deals",
                headers=headers,
                params={
                    "status": "eq.pending",
                    "select": "value,currency,name,client_name",
                },
            )
            pending = resp2.json() if resp2.status_code == 200 else []
            pipeline_value = sum(d.get("value", 0) for d in pending)

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "💰 Weekly Revenue Report", "emoji": True},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*MTD Revenue:* UGX {total_revenue:,.0f}"},
                    {"type": "mrkdwn", "text": f"*Deals Closed:* {deal_count}"},
                    {"type": "mrkdwn", "text": f"*Pipeline Value:* UGX {pipeline_value:,.0f}"},
                    {"type": "mrkdwn", "text": f"*Pending Deals:* {len(pending)}"},
                ],
            },
        ]

        if deals:
            deal_text = "\n".join([
                f"  • {d.get('name', '')} — {d.get('client_name', '')} (UGX {d.get('value', 0):,.0f})"
                for d in deals[:5]
            ])
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Closed This Month:*\n{deal_text}"},
            })

        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"🕐 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}],
        })

        _send_slack_message(AGENT_CHANNELS["revenue"], "Weekly revenue report", blocks)
        logger.info("[Revenue Tracker] Report sent.")

    except Exception as e:
        logger.error(f"[Revenue Tracker] Error: {e}")


# ── Agent Registry ──────────────────────────────────────────────────────

AGENTS = {
    "lead_scanner": {
        "func": scan_new_leads,
        "schedule": "interval",
        "hours": 6,
        "description": "Check for new leads every 6 hours",
    },
    "pipeline_monitor": {
        "func": monitor_pipeline,
        "schedule": "cron",
        "hour": 9,
        "minute": 0,
        "description": "Daily pipeline health check at 9 AM",
    },
    "system_health": {
        "func": check_system_health,
        "schedule": "cron",
        "hour": 8,
        "minute": 30,
        "description": "Daily system health check at 8:30 AM",
    },
    "revenue_tracker": {
        "func": track_revenue,
        "schedule": "cron",
        "day_of_week": "mon",
        "hour": 10,
        "minute": 0,
        "description": "Weekly revenue report on Monday at 10 AM",
    },
}


def start_proactive_agents():
    """
    Start all proactive agents using APScheduler.
    Call this from the DAWN API startup event.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()

        for name, config in AGENTS.items():
            func = config["func"]
            schedule_type = config["schedule"]

            if schedule_type == "interval":
                scheduler.add_job(
                    func,
                    "interval",
                    hours=config["hours"],
                    id=name,
                    name=name,
                    replace_existing=True,
                )
            elif schedule_type == "cron":
                kwargs = {"id": name, "name": name, "replace_existing": True}
                if "hour" in config:
                    kwargs["hour"] = config["hour"]
                if "minute" in config:
                    kwargs["minute"] = config["minute"]
                if "day_of_week" in config:
                    kwargs["day_of_week"] = config["day_of_week"]
                scheduler.add_job(func, "cron", **kwargs)

            logger.info(f"[Proactive Agents] Registered: {name} — {config['description']}")

        scheduler.start()
        logger.info("[Proactive Agents] All agents started.")
        return scheduler

    except ImportError:
        logger.warning(
            "[Proactive Agents] APScheduler not installed. "
            "Install with: pip install apscheduler"
        )
        return None
    except Exception as e:
        logger.error(f"[Proactive Agents] Failed to start: {e}")
        return None
