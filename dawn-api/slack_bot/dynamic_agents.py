"""
Dynamic Proactive Agents — user-configurable scheduled agents.

Unlike the hardcoded proactive_agents.py, these agents are created,
configured, and managed by users via Slack commands.

Agent Types:
  1. keyword_monitor — Watch a channel for specific keywords, alert when found
  2. cron_report — Run a DAWN query on a schedule and post results to a channel
  3. threshold_alert — Monitor a metric and alert when it crosses a threshold

Each agent is persisted to the Supabase `dynamic_agents` table and
managed by the DynamicAgentManager singleton.
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from slack_sdk import WebClient

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
DAWN_API_URL = os.environ.get("DAWN_API_URL", "http://localhost:8000")
DAWN_API_KEY = os.environ.get("DAWN_API_KEY", "dev-key")


class AgentType(str, Enum):
    KEYWORD_MONITOR = "keyword_monitor"
    CRON_REPORT = "cron_report"
    THRESHOLD_ALERT = "threshold_alert"


class AgentStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"


# In-memory store (loaded from DB on startup)
_active_agents: dict[str, dict] = {}


def _slack_client() -> Optional[WebClient]:
    if not SLACK_BOT_TOKEN:
        return None
    return WebClient(token=SLACK_BOT_TOKEN)


def _send_slack_message(channel: str, text: str):
    """Send a message to a Slack channel."""
    client = _slack_client()
    if not client:
        logger.warning("Cannot send Slack message: no token")
        return
    try:
        client.chat_postMessage(channel=channel, text=text)
    except Exception as e:
        logger.error(f"Failed to send Slack message to #{channel}: {e}")


# ── Database Operations ────────────────────────────────────────────────────

async def _get_db():
    """Get a database connection for agent persistence."""
    try:
        from db.client import get_db
        async for conn in get_db():
            return conn
    except Exception as e:
        logger.error(f"Failed to get DB connection: {e}")
        return None


async def load_agents_from_db():
    """Load all active agents from the database into memory."""
    global _active_agents
    conn = await _get_db()
    if not conn:
        logger.warning("Cannot load dynamic agents: no DB connection")
        return

    try:
        result = await conn.fetch(
            "SELECT * FROM dynamic_agents WHERE status = 'active' ORDER BY created_at DESC"
        )
        _active_agents = {}
        for row in result:
            agent = dict(row)
            _active_agents[agent["id"]] = agent
        logger.info(f"Loaded {len(_active_agents)} dynamic agents from database")
    except Exception as e:
        logger.error(f"Failed to load dynamic agents: {e}")


async def save_agent_to_db(agent: dict) -> bool:
    """Save a new agent to the database."""
    conn = await _get_db()
    if not conn:
        return False

    try:
        await conn.execute(
            """
            INSERT INTO dynamic_agents (id, name, agent_type, config, channel, status, created_by, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            agent["id"],
            agent["name"],
            agent["agent_type"],
            json.dumps(agent.get("config", {})),
            agent.get("channel", ""),
            agent.get("status", "active"),
            agent.get("created_by", "slack"),
            datetime.now(timezone.utc),
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save agent to DB: {e}")
        return False


async def update_agent_status(agent_id: str, status: str) -> bool:
    """Update an agent's status in the database."""
    conn = await _get_db()
    if not conn:
        return False

    try:
        await conn.execute(
            "UPDATE dynamic_agents SET status = $1, updated_at = $2 WHERE id = $3",
            status,
            datetime.now(timezone.utc),
            agent_id,
        )
        if agent_id in _active_agents:
            if status == "deleted":
                del _active_agents[agent_id]
            else:
                _active_agents[agent_id]["status"] = status
        return True
    except Exception as e:
        logger.error(f"Failed to update agent status: {e}")
        return False


# ── Agent Execution ────────────────────────────────────────────────────────

async def execute_keyword_monitor(agent: dict):
    """Check recent messages in the monitored channel for keywords."""
    config = agent.get("config", {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = {}

    channel = agent.get("channel", "")
    keywords = config.get("keywords", [])
    if not channel or not keywords:
        return

    client = _slack_client()
    if not client:
        return

    try:
        # Get recent messages
        result = client.conversations_history(channel=channel, limit=20)
        messages = result.get("messages", [])

        found = []
        for msg in messages:
            text = msg.get("text", "")
            if msg.get("bot_id"):
                continue
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    found.append({
                        "user": msg.get("user", "unknown"),
                        "text": text[:200],
                        "ts": msg.get("ts", ""),
                    })
                    break

        if found:
            blocks = [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"🔍 Keyword Alert: {', '.join(keywords)}", "emoji": True},
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"Found {len(found)} matching messages in <#{channel}>:"},
                },
            ]
            for item in found[:5]:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"• <{item.get('ts', '')}|Message> from <@{item['user']}>: _{item['text'][:100]}_"},
                })
            if len(found) > 5:
                blocks.append({
                    "type": "context",
                    "elements": [{"type": "mrkdwn", "text": f"...and {len(found) - 5} more"}],
                })

            _send_slack_message(channel, f"Keyword alert: {len(found)} matches", blocks)

    except Exception as e:
        logger.error(f"Keyword monitor error for agent {agent.get('id')}: {e}")


async def execute_cron_report(agent: dict):
    """Run a DAWN query and post the result to a channel."""
    config = agent.get("config", {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = {}

    channel = agent.get("channel", "")
    query = config.get("query", "")
    if not channel or not query:
        return

    try:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{DAWN_API_URL}/agent/",
                json={"message": query, "max_iterations": 10},
                headers={"x-api-key": DAWN_API_KEY},
            )
            if resp.status_code == 200:
                # Parse SSE response
                full_text = ""
                for line in resp.text.split("\n"):
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "token":
                                full_text += data.get("content", "")
                        except json.JSONDecodeError:
                            continue

                result = full_text.strip() or "No output produced."
                header = f"📊 *Scheduled Report: {agent.get('name', 'Untitled')}*"
                _send_slack_message(channel, f"{header}\n\n{result[:3000]}")
            else:
                _send_slack_message(channel, f"⚠️ Scheduled report failed: HTTP {resp.status_code}")

    except Exception as e:
        logger.error(f"Cron report error for agent {agent.get('id')}: {e}")
        _send_slack_message(channel, f"⚠️ Scheduled report error: {e}")


async def execute_threshold_alert(agent: dict):
    """Check a metric and alert if it crosses a threshold."""
    config = agent.get("config", {})
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            config = {}

    channel = agent.get("channel", "")
    metric = config.get("metric", "")
    threshold = config.get("threshold", 0)
    direction = config.get("direction", "above")  # "above" or "below"

    if not channel or not metric:
        return

    try:
        # Get the metric value
        value = None
        if metric == "disk_usage":
            import shutil
            usage = shutil.disk_usage("/")
            value = (usage.used / usage.total) * 100
        elif metric == "api_health":
            import httpx
            resp = await httpx.get(f"{DAWN_API_URL}/health", timeout=5.0)
            value = 1 if resp.status_code == 200 else 0
            threshold = 1  # Alert if not healthy
            direction = "below"

        if value is None:
            logger.warning(f"Unknown metric for threshold alert: {metric}")
            return

        # Check threshold
        triggered = False
        if direction == "above" and value > threshold:
            triggered = True
        elif direction == "below" and value < threshold:
            triggered = True

        if triggered:
            emoji = "🔴" if direction == "above" else "🔵"
            _send_slack_message(
                channel,
                f"{emoji} *Threshold Alert: {metric}*\n"
                f"Current value: {value:.1f}\n"
                f"Threshold: {direction} {threshold}\n"
                f"Agent: {agent.get('name', 'Untitled')}",
            )

    except Exception as e:
        logger.error(f"Threshold alert error for agent {agent.get('id')}: {e}")


# ── Agent Manager ──────────────────────────────────────────────────────────

class DynamicAgentManager:
    """Manages the lifecycle of dynamic proactive agents."""

    @staticmethod
    async def create_agent(
        name: str,
        agent_type: str,
        channel: str,
        config: dict,
        created_by: str = "slack",
    ) -> dict:
        """Create a new dynamic agent."""
        import uuid
        agent = {
            "id": str(uuid.uuid4()),
            "name": name,
            "agent_type": agent_type,
            "channel": channel,
            "config": config,
            "status": "active",
            "created_by": created_by,
        }

        saved = await save_agent_to_db(agent)
        if saved:
            _active_agents[agent["id"]] = agent
            logger.info(f"Created dynamic agent: {name} ({agent_type}) in #{channel}")
            return {"success": True, "agent": agent}
        else:
            return {"success": False, "error": "Failed to save agent to database"}

    @staticmethod
    async def delete_agent(agent_id: str) -> dict:
        """Delete a dynamic agent."""
        success = await update_agent_status(agent_id, "deleted")
        if success:
            return {"success": True, "message": "Agent deleted"}
        return {"success": False, "error": "Agent not found or could not be deleted"}

    @staticmethod
    async def toggle_agent(agent_id: str) -> dict:
        """Toggle an agent between active and paused."""
        agent = _active_agents.get(agent_id)
        if not agent:
            return {"success": False, "error": "Agent not found"}

        new_status = "paused" if agent.get("status") == "active" else "active"
        success = await update_agent_status(agent_id, new_status)
        if success:
            return {"success": True, "status": new_status}
        return {"success": False, "error": "Failed to update agent status"}

    @staticmethod
    def list_agents(status: Optional[str] = None) -> list[dict]:
        """List all dynamic agents, optionally filtered by status."""
        agents = list(_active_agents.values())
        if status:
            agents = [a for a in agents if a.get("status") == status]
        return agents

    @staticmethod
    def get_agent(agent_id: str) -> Optional[dict]:
        """Get a specific agent by ID."""
        return _active_agents.get(agent_id)


# ── Scheduler Integration ──────────────────────────────────────────────────

async def run_due_agents():
    """Check all active agents and run any that are due.
    
    Called by the APScheduler on a regular interval (e.g., every 5 minutes).
    """
    for agent_id, agent in _active_agents.items():
        if agent.get("status") != "active":
            continue

        agent_type = agent.get("agent_type", "")
        try:
            if agent_type == AgentType.KEYWORD_MONITOR.value:
                await execute_keyword_monitor(agent)
            elif agent_type == AgentType.CRON_REPORT.value:
                await execute_cron_report(agent)
            elif agent_type == AgentType.THRESHOLD_ALERT.value:
                await execute_threshold_alert(agent)
        except Exception as e:
            logger.error(f"Failed to run agent {agent_id}: {e}")


def start_dynamic_agent_scheduler():
    """Start the scheduler that runs dynamic agents on their intervals.
    
    Call this from the DAWN API startup event.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()

        # Run keyword monitors every 10 minutes
        scheduler.add_job(
            lambda: asyncio.run(run_due_agents()),
            "interval",
            minutes=10,
            id="dynamic_agents",
            name="Dynamic Agent Runner",
            replace_existing=True,
        )

        scheduler.start()
        logger.info("[Dynamic Agents] Scheduler started (every 10 minutes)")
        return scheduler
    except ImportError:
        logger.warning("[Dynamic Agents] APScheduler not installed")
        return None
    except Exception as e:
        logger.error(f"[Dynamic Agents] Failed to start scheduler: {e}")
        return None
