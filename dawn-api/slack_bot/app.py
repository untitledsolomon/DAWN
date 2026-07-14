"""
Slack Bolt App — Socket Mode, no public endpoint needed.
Runs as a background process alongside the DAWN API.

Architecture:
  Slack (Socket Mode) → SlackBoltApp → DAWN Agent API (HTTP) → Full DAWN agent with tools

This replaces the old chat-mode proxy with a direct connection to DAWN's
agent endpoint, giving you the full DAWN experience (tools, knowledge graph,
file analysis, decision workflows, etc.) from within Slack.

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
import re
import tempfile
from typing import Optional

from slack_bolt import Ack
from slack_sdk import WebClient

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────

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


# ── Session UUID Mapping ───────────────────────────────────────────────────

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


# ── App Factory ────────────────────────────────────────────────────────────

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


# ── DAWN Agent API ─────────────────────────────────────────────────────────

async def query_dawn_agent(
    message: str,
    session_id: Optional[str] = None,
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
) -> str:
    """
    Send a message to DAWN's AGENT endpoint (not the chat endpoint).

    This gives you full tool access: knowledge graph, filesystem, git,
    web search, OMNI, OSINT, pentest, decision workflows, ontology, etc.

    If file_url and file_name are provided, the file is first ingested
    into DAWN's knowledge graph, then the agent is asked about it.
    """
    try:
        # ── Step 1: If there's a file, ingest it first ──
        if file_url and file_name:
            ingest_result = await _ingest_slack_file(file_url, file_name)
            if ingest_result.get("error"):
                return f"⚠️ Could not process file: {ingest_result['error']}"
            # Prepend context about the ingested file to the message
            file_context = (
                f"[I've ingested the file '{file_name}' into my knowledge graph. "
                f"Its content is now available for analysis.]\n\n"
            )
            message = file_context + message

        # ── Step 2: Call the agent endpoint ──
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "message": message,
                "session_id": session_id,
                "max_iterations": 15,
            }
            resp = await client.post(
                f"{DAWN_API_URL}/agent/",
                json=payload,
                headers={
                    "x-api-key": DAWN_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code != 200:
                logger.error(f"DAWN Agent API error: {resp.status_code} {resp.text[:300]}")
                return f"⚠️ DAWN Agent API returned {resp.status_code}. Check logs."

            # Parse SSE stream — collect all tokens and artifacts
            full_text = ""
            artifacts = []
            for line in resp.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("type", "")
                        if event_type == "token":
                            full_text += data.get("content", "")
                        elif event_type == "artifact":
                            artifacts.append(data)
                        elif event_type == "done":
                            break
                    except json.JSONDecodeError:
                        continue

            result = full_text.strip()

            # Append artifact links if any were created
            if artifacts:
                result += "\n\n📎 *Artifacts created:*\n"
                for art in artifacts:
                    art_type = art.get("artifact_type", "file")
                    art_title = art.get("title", "Untitled")
                    art_id = art.get("artifact_id", "")
                    if art_id:
                        result += f"  • [{art_type}] {art_title} (ID: `{art_id[:8]}...`)\n"

            return result or "🤖 DAWN processed your message but returned no text."

    except httpx.RequestError as e:
        logger.error(f"DAWN Agent API connection failed: {e}")
        return f"⚠️ Could not reach DAWN Agent API: {e}"
    except Exception as e:
        logger.error(f"Unexpected error querying DAWN agent: {e}")
        return f"⚠️ Unexpected error: {e}"


async def _ingest_slack_file(file_url: str, file_name: str) -> dict:
    """
    Download a file from Slack and ingest it into DAWN's knowledge graph.

    Returns {"success": True, "job_id": "..."} or {"error": "..."}.
    """
    try:
        # Download the file from Slack
        async with httpx.AsyncClient(timeout=60.0) as client:
            file_resp = await client.get(
                file_url,
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            )
            if file_resp.status_code != 200:
                return {"error": f"Failed to download file from Slack: HTTP {file_resp.status_code}"}

            file_bytes = file_resp.content

        # Upload to DAWN's ingestion endpoint
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": (file_name, file_bytes)}
            ingest_resp = await client.post(
                f"{DAWN_API_URL}/ingest/file",
                files=files,
                data={"title": file_name},
                headers={"x-api-key": DAWN_API_KEY},
            )
            if ingest_resp.status_code != 200:
                return {"error": f"Ingestion failed: HTTP {ingest_resp.status_code} - {ingest_resp.text[:200]}"}

            result = ingest_resp.json()
            logger.info(f"Ingested Slack file '{file_name}' → job {result.get('job_id', '?')}")
            return {"success": True, "job_id": result.get("job_id", "")}

    except Exception as e:
        logger.error(f"File ingestion error: {e}")
        return {"error": str(e)}


async def _download_slack_file(file_url: str) -> Optional[bytes]:
    """Download a file from Slack's URL using the bot token."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(
                file_url,
                headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            )
            if resp.status_code == 200:
                return resp.content
            logger.error(f"Failed to download Slack file: HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"Slack file download error: {e}")
        return None


async def _send_blocks(channel: str, blocks: list, text: str = ""):
    """Send a Block Kit message to a Slack channel."""
    try:
        client = WebClient(token=SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel, blocks=blocks, text=text)
    except Exception as e:
        logger.error(f"Failed to send blocks to {channel}: {e}")


async def _send_long_message(channel: str, text: str, thread_ts: Optional[str] = None):
    """
    Send a message, splitting into multiple messages if it exceeds Slack's
    40,000 character limit.
    """
    MAX_LENGTH = 39000
    client = WebClient(token=SLACK_BOT_TOKEN)

    if len(text) <= MAX_LENGTH:
        kwargs = {"channel": channel, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)
        return

    # Split into chunks at paragraph boundaries where possible
    chunks = []
    current = ""
    for paragraph in text.split("\n\n"):
        if len(current) + len(paragraph) + 2 > MAX_LENGTH:
            chunks.append(current.strip())
            current = paragraph + "\n\n"
        else:
            current += paragraph + "\n\n"
    if current.strip():
        chunks.append(current.strip())

    for i, chunk in enumerate(chunks):
        header = f"*Part {i+1}/{len(chunks)}*\n\n" if len(chunks) > 1 else ""
        kwargs = {"channel": channel, "text": header + chunk}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        client.chat_postMessage(**kwargs)


# ── Handler Registration ───────────────────────────────────────────────────

def _register_handlers(app):
    """Register all event handlers and slash commands on the Bolt app."""

    @app.event("app_mention")
    def handle_mention(event: dict, say, client: WebClient):
        """When someone @DAWN in a channel."""
        try:
            text = event.get("text", "")
            text = re.sub(r"<@\w+>", "", text).strip()

            if not text:
                say("👋 Hi! What can I help you with?")
                return

            channel = event.get("channel", "")
            session_id = get_or_create_session_id(channel)

            # Check for attached files
            files = event.get("files", [])
            file_url = None
            file_name = None
            if files:
                file_url = files[0].get("url_private_download") or files[0].get("url_private")
                file_name = files[0].get("name", "file")

            response = asyncio.run(query_dawn_agent(
                text,
                session_id=session_id,
                file_url=file_url,
                file_name=file_name,
            ))
            asyncio.run(_send_long_message(channel, response))

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

            # Check for attached files
            files = event.get("files", [])
            file_url = None
            file_name = None
            if files:
                file_url = files[0].get("url_private_download") or files[0].get("url_private")
                file_name = files[0].get("name", "file")

            response = asyncio.run(query_dawn_agent(
                text,
                session_id=session_id,
                file_url=file_url,
                file_name=file_name,
            ))
            asyncio.run(_send_long_message(channel, response))

        except Exception as e:
            logger.error(f"Error in handle_dm: {e}", exc_info=True)

    @app.command("/dawn")
    def handle_dawn_command(ack: Ack, command: dict, say):
        """Generic /dawn command — routes to the full DAWN agent."""
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/dawn <your question or command>`")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn_agent(text, session_id=session_id))
        asyncio.run(_send_long_message(channel, response))

    @app.command("/status")
    def handle_status(ack: Ack, say):
        """Quick system status check via the agent."""
        ack()
        try:
            session_id = get_or_create_session_id("_system_status")
            resp = asyncio.run(query_dawn_agent(
                "Run a quick system health check. Check the database, knowledge graph, "
                "and infrastructure. Return a concise status report.",
                session_id=session_id,
            ))
            say(f"📊 *DAWN System Status*\n{resp}")
        except Exception as e:
            say(f"⚠️ Status check failed: {e}")

    @app.command("/revenue")
    def handle_revenue(ack: Ack, say):
        """Quick revenue summary via the agent."""
        ack()
        try:
            session_id = get_or_create_session_id("_system_revenue")
            resp = asyncio.run(query_dawn_agent(
                "What's the current revenue situation? Summarize active clients, "
                "monthly recurring revenue, and any overdue invoices. Use the knowledge "
                "graph and any available data sources.",
                session_id=session_id,
            ))
            say(f"💰 *Revenue Summary*\n{resp}")
        except Exception as e:
            say(f"⚠️ Revenue check failed: {e}")

    @app.command("/regent")
    def handle_regent(ack: Ack, command: dict, say):
        """Ask DAWN about anything Regent-related."""
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/regent <your question about Regent>`\n"
                "Examples:\n"
                "• `/regent what's the status of the Axis ERP project?`\n"
                "• `/regent who's working on the CRM integration?`\n"
                "• `/regent summarize our active clients and their projects`\n"
                "• `/regent what's our tech stack?`")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn_agent(
            f"[Regent context] {text}",
            session_id=session_id,
        ))
        asyncio.run(_send_long_message(channel, response))

    @app.command("/analyze")
    def handle_analyze(ack: Ack, command: dict, say):
        """Analyze something — a file, a situation, data."""
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/analyze <what do you want me to analyze?>`\n"
                "Tip: Share a file in the thread first, then `/analyze` it.")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn_agent(
            f"[Analysis request] {text}",
            session_id=session_id,
        ))
        asyncio.run(_send_long_message(channel, response))

    # ── v37.0: New Slash Commands ──────────────────────────────────────────

    @app.command("/watch")
    def handle_watch(ack: Ack, command: dict, say):
        """Create a keyword monitor agent.
        
        Usage: /watch #channel for "keyword1, keyword2" every 10min
        """
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/watch #channel for \"keywords\" every <interval>`\n"
                "Example: `/watch #support for \"urgent, escalation, critical\" every 10min`")
            return

        # Parse: #channel for "keywords" every Nmin
        channel_match = re.search(r"#(\w+)", text)
        keywords_match = re.search(r'"([^"]+)"', text)
        interval_match = re.search(r"every\s+(\d+)\s*min", text, re.IGNORECASE)

        if not channel_match or not keywords_match:
            say("Usage: `/watch #channel for \"keywords\" every 10min`\n"
                "Example: `/watch #support for \"urgent, escalation\" every 10min`")
            return

        channel_name = channel_match.group(1)
        keywords = [k.strip() for k in keywords_match.group(1).split(",")]
        interval_min = int(interval_match.group(1)) if interval_match else 10

        try:
            from slack_bot.dynamic_agents import DynamicAgentManager
            result = asyncio.run(DynamicAgentManager.create_agent(
                name=f"watch-{channel_name}",
                agent_type="keyword_monitor",
                channel=channel_name,
                config={"keywords": keywords, "interval_minutes": interval_min},
                created_by=command.get("user_id", "slack"),
            ))
            if result["success"]:
                say(f"✅ Created keyword monitor for #{channel_name}\n"
                    f"   Keywords: {', '.join(keywords)}\n"
                    f"   Interval: every {interval_min} minutes\n"
                    f"   Agent ID: `{result['agent']['id'][:8]}...`")
            else:
                say(f"⚠️ Failed to create monitor: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error creating watch agent: {e}")
            say(f"⚠️ Error: {e}")

    @app.command("/agents")
    def handle_agents(ack: Ack, command: dict, say):
        """List and manage dynamic agents.
        
        Usage: /agents — list all agents
               /agents stop <id> — pause an agent
               /agents start <id> — resume an agent
               /agents delete <id> — delete an agent
        """
        ack()
        text = command.get("text", "").strip()
        parts = text.split()

        try:
            from slack_bot.dynamic_agents import DynamicAgentManager

            if not text:
                # List all agents
                agents = DynamicAgentManager.list_agents()
                if not agents:
                    say("No dynamic agents configured. Use `/watch` to create one.")
                    return

                blocks = [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": "🤖 Dynamic Agents", "emoji": True},
                    },
                    {"type": "divider"},
                ]

                for agent in agents:
                    status_emoji = "🟢" if agent.get("status") == "active" else "⏸️"
                    agent_type = agent.get("agent_type", "unknown").replace("_", " ").title()
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{status_emoji} *{agent.get('name', 'Unnamed')}*\n"
                                f"   Type: {agent_type} | Channel: #{agent.get('channel', '?')}\n"
                                f"   ID: `{agent.get('id', '?')[:8]}...`"
                            ),
                        },
                    })

                say(text="Dynamic Agents", blocks=blocks)
                return

            if parts[0] == "stop" and len(parts) >= 2:
                result = asyncio.run(DynamicAgentManager.toggle_agent(parts[1]))
                if result["success"]:
                    say(f"⏸️ Agent paused.")
                else:
                    say(f"⚠️ {result.get('error', 'Failed to pause agent')}")

            elif parts[0] == "start" and len(parts) >= 2:
                result = asyncio.run(DynamicAgentManager.toggle_agent(parts[1]))
                if result["success"]:
                    say(f"▶️ Agent resumed.")
                else:
                    say(f"⚠️ {result.get('error', 'Failed to resume agent')}")

            elif parts[0] == "delete" and len(parts) >= 2:
                result = asyncio.run(DynamicAgentManager.delete_agent(parts[1]))
                if result["success"]:
                    say(f"🗑️ Agent deleted.")
                else:
                    say(f"⚠️ {result.get('error', 'Failed to delete agent')}")

            else:
                say("Usage:\n"
                    "  `/agents` — list all agents\n"
                    "  `/agents stop <id>` — pause an agent\n"
                    "  `/agents start <id>` — resume an agent\n"
                    "  `/agents delete <id>` — delete an agent")

        except Exception as e:
            logger.error(f"Error in /agents: {e}")
            say(f"⚠️ Error: {e}")

    @app.command("/axis")
    def handle_axis(ack: Ack, command: dict, say):
        """Query Axis ERP — payroll, tax, employees.
        
        Usage: /axis <question about payroll, tax, or employees>
        """
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/axis <your question about payroll, tax, or employees>`\n"
                "Examples:\n"
                "• `/axis process payroll for January 2025`\n"
                "• `/axis what's the PAYE for a gross salary of 5,000,000 UGX?`\n"
                "• `/axis list all employees`\n"
                "• `/axis show me the tax report for last month`")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn_agent(
            f"[Axis ERP] {text}",
            session_id=session_id,
        ))
        asyncio.run(_send_long_message(channel, response))

    @app.command("/forge")
    def handle_forge(ack: Ack, command: dict, say):
        """Query Forge CMS — website content management.
        
        Usage: /forge <question about website content>
        """
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/forge <your question about website content>`\n"
                "Examples:\n"
                "• `/forge list all pages`\n"
                "• `/forge create a new blog post about our services`\n"
                "• `/forge what's our top performing content?`\n"
                "• `/forge update the homepage hero section`")
            return

        channel = command.get("channel_id", "")
        session_id = get_or_create_session_id(channel)

        response = asyncio.run(query_dawn_agent(
            f"[Forge CMS] {text}",
            session_id=session_id,
        ))
        asyncio.run(_send_long_message(channel, response))

    @app.command("/report")
    def handle_report(ack: Ack, command: dict, say):
        """Schedule a recurring report.
        
        Usage: /report "query" every <schedule>
        """
        ack()
        text = command.get("text", "").strip()
        if not text:
            say("Usage: `/report \"your query\" every <schedule>`\n"
                "Examples:\n"
                "• `/report \"summarize this week's leads\" every monday 9am`\n"
                "• `/report \"check system health\" every 6 hours`\n"
                "• `/report \"revenue summary\" every 1st of month`")
            return

        # Parse: "query" every <schedule>
        query_match = re.search(r'"([^"]+)"', text)
        if not query_match:
            say("Please put your query in quotes.\n"
                "Example: `/report \"summarize leads\" every monday 9am`")
            return

        query = query_match.group(1)
        schedule_text = text[text.index(query_match.group(0)) + len(query_match.group(0)):].strip()
        schedule_text = re.sub(r"^every\s+", "", schedule_text, flags=re.IGNORECASE).strip()

        if not schedule_text:
            say("Please specify a schedule.\n"
                "Example: `/report \"summarize leads\" every monday 9am`")
            return

        channel = command.get("channel_id", "")
        channel_name = command.get("channel_name", channel)

        try:
            from slack_bot.dynamic_agents import DynamicAgentManager
            result = asyncio.run(DynamicAgentManager.create_agent(
                name=f"report-{schedule_text[:20].replace(' ', '-')}",
                agent_type="cron_report",
                channel=channel_name,
                config={"query": query, "schedule": schedule_text},
                created_by=command.get("user_id", "slack"),
            ))
            if result["success"]:
                say(f"✅ Scheduled report created\n"
                    f"   Query: \"{query[:100]}\"\n"
                    f"   Schedule: every {schedule_text}\n"
                    f"   Channel: #{channel_name}\n"
                    f"   Agent ID: `{result['agent']['id'][:8]}...`")
            else:
                say(f"⚠️ Failed to create report: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error creating report: {e}")
            say(f"⚠️ Error: {e}")

    # ── CRM Agent Commands (kept for backward compatibility) ──

    @app.command("/leads")
    def handle_leads(ack: Ack, command: dict, say):
        """CRM lead management — now routed through the full agent."""
        ack()
        try:
            from slack_bot.agents import handle_leads_command
            text = command.get("text", "")
            channel = command.get("channel_id", "")
            result_text, blocks = asyncio.run(handle_leads_command(text))

            if blocks:
                asyncio.run(_send_blocks(channel, blocks, text=result_text or "Leads"))
            else:
                say(result_text or "No leads data available.")
        except Exception as e:
            logger.error(f"Error in /leads: {e}", exc_info=True)
            say(f"⚠️ Error fetching leads: {str(e)[:200]}")

    @app.command("/team")
    def handle_team(ack: Ack, command: dict, say):
        """Team roster management."""
        ack()
        try:
            from slack_bot.agents import handle_team_command
            text = command.get("text", "")
            channel = command.get("channel_id", "")
            result_text, blocks = asyncio.run(handle_team_command(text))

            if blocks:
                asyncio.run(_send_blocks(channel, blocks, text=result_text or "Team"))
            else:
                say(result_text or "No team data available.")
        except Exception as e:
            logger.error(f"Error in /team: {e}", exc_info=True)
            say(f"⚠️ Error: {str(e)[:200]}")

    @app.command("/projects")
    def handle_projects(ack: Ack, command: dict, say):
        """Project management."""
        ack()
        try:
            from slack_bot.agents import handle_projects_command
            text = command.get("text", "")
            channel = command.get("channel_id", "")
            result_text, blocks = asyncio.run(handle_projects_command(text))

            if blocks:
                asyncio.run(_send_blocks(channel, blocks, text=result_text or "Projects"))
            else:
                say(result_text or "No project data available.")
        except Exception as e:
            logger.error(f"Error in /projects: {e}", exc_info=True)
            say(f"⚠️ Error: {str(e)[:200]}")

    @app.command("/pipeline")
    def handle_pipeline(ack: Ack, command: dict, say):
        """Pipeline funnel summary."""
        ack()
        try:
            from slack_bot.agents import handle_pipeline_command
            channel = command.get("channel_id", "")
            result_text, blocks = asyncio.run(handle_pipeline_command())

            if blocks:
                asyncio.run(_send_blocks(channel, blocks, text=result_text or "Pipeline"))
            else:
                say(result_text or "No pipeline data available.")
        except Exception as e:
            logger.error(f"Error in /pipeline: {e}", exc_info=True)
            say(f"⚠️ Error: {str(e)[:200]}")

    @app.command("/dashboard")
    def handle_dashboard(ack: Ack, command: dict, say):
        """Full team dashboard."""
        ack()
        try:
            from slack_bot.agents import handle_dashboard_command
            channel = command.get("channel_id", "")
            result_text, blocks = asyncio.run(handle_dashboard_command())

            if blocks:
                asyncio.run(_send_blocks(channel, blocks, text=result_text or "Dashboard"))
            else:
                say(result_text or "No dashboard data available.")
        except Exception as e:
            logger.error(f"Error in /dashboard: {e}", exc_info=True)
            say(f"⚠️ Error: {str(e)[:200]}")

    # ── Channel Monitoring ─────────────────────────────────────────────────

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


# ── Startup ────────────────────────────────────────────────────────────────

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
