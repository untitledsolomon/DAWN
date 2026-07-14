"""
Slack Bot Agent Handlers — specialized command handlers for CRM, Team, Projects.

Each handler is a standalone function that:
1. Receives the Slack command context
2. Calls the DAWN CRM Agent API (internal HTTP)
3. Formats the response as a Slack Block Kit message
4. Returns the formatted message

These are registered in slack_bot/app.py alongside the existing handlers.
"""

import os
import json
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

DAWN_API_URL = os.environ.get("DAWN_API_URL", "http://localhost:8000")
DAWN_API_KEY = os.environ.get("DAWN_API_KEY", "dev-key")

# ── Helpers ─────────────────────────────────────────────────────────────

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
            logger.error(f"CRM API GET {path} failed: {resp.status_code} {resp.text[:200]}")
            return {"error": f"API returned {resp.status_code}"}
        return resp.json()

async def _crm_api_post(path: str, data: dict) -> dict:
    """POST to DAWN's internal CRM agent endpoint."""
    url = f"{DAWN_API_URL}/crm{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            json=data,
            headers={
                "x-api-key": DAWN_API_KEY,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code != 200:
            logger.error(f"CRM API POST {path} failed: {resp.status_code} {resp.text[:200]}")
            return {"error": f"API returned {resp.status_code}"}
        return resp.json()

# ── Formatting Helpers ──────────────────────────────────────────────────

def _status_emoji(status: str) -> str:
    emojis = {
        "new": "🆕",
        "contacted": "🔵",
        "follow-up": "🟡",
        "interested": "🟠",
        "closed": "🟢",
        "active": "🟢",
        "paused": "⏸️",
        "completed": "✅",
        "draft": "📝",
    }
    return emojis.get(status.lower(), "•")

def _pipeline_block(data: dict) -> list:
    """Format pipeline summary as Slack blocks."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 Pipeline Summary", "emoji": True},
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"🆕 *New:* {data.get('new_leads', 0)}"},
                {"type": "mrkdwn", "text": f"🔵 *Contacted:* {data.get('contacted', 0)}"},
                {"type": "mrkdwn", "text": f"🟡 *Follow-up:* {data.get('follow_up', 0)}"},
                {"type": "mrkdwn", "text": f"🟠 *Interested:* {data.get('interested', 0)}"},
                {"type": "mrkdwn", "text": f"🟢 *Closed:* {data.get('closed', 0)}"},
                {"type": "mrkdwn", "text": f"📊 *Total:* {data.get('total_leads', 0)}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"📈 *Conversion Rate:* {data.get('conversion_rate', 0)}%"},
                {"type": "mrkdwn", "text": f"📬 *Reply Rate:* {data.get('reply_rate', 0)}%"},
            ],
        },
    ]

    # Sources
    sources = data.get("leads_by_source", {})
    if sources:
        source_text = "\n".join([f"  • *{k}:* {v}" for k, v in sorted(sources.items(), key=lambda x: -x[1])])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Top Sources:*\n{source_text}"},
        })

    # Campaigns
    blocks.append({
        "type": "section",
        "fields": [
            {"type": "mrkdwn", "text": f"📋 *Campaigns:* {data.get('total_campaigns', 0)} total, {data.get('active_campaigns', 0)} active"},
            {"type": "mrkdwn", "text": f"✉️ *Sent:* {data.get('total_sent', 0)}"},
        ],
    })

    # Recent leads
    recent = data.get("recent_leads", [])
    if recent:
        recent_text = "\n".join([
            f"  • {r.get('name', 'Unknown')} — {r.get('business', '')} ({_status_emoji(r.get('status', ''))})"
            for r in recent[:5]
        ])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Recent Leads:*\n{recent_text}"},
        })

    return blocks

def _leads_list_block(data: dict, title: str = "Leads") -> list:
    """Format a list of leads as Slack blocks."""
    leads = data.get("leads", [])
    total = data.get("total", len(leads))

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📋 {title} ({total})", "emoji": True},
        },
        {"type": "divider"},
    ]

    if not leads:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "No leads found."},
        })
        return blocks

    for lead in leads[:10]:  # Max 10 per message
        name = lead.get("name", "Unknown")
        business = lead.get("business", "")
        status = lead.get("status", "new")
        source = lead.get("source", "")
        score = lead.get("score", 0)
        email = lead.get("email", "")

        text = f"{_status_emoji(status)} *{name}*"
        if business:
            text += f" — {business}"
        text += f"\n   Status: *{status}* | Score: {score}"
        if source:
            text += f" | Source: {source}"
        if email:
            text += f"\n   📧 {email}"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

    if len(leads) > 10:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Showing 10 of {len(leads)} leads. Use `/leads --limit N` for more."}],
        })

    return blocks

def _team_block(data: dict) -> list:
    """Format team roster as Slack blocks."""
    members = data.get("members", [])

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "👥 Regent Team", "emoji": True},
        },
        {"type": "divider"},
    ]

    if not members:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "No team members registered yet. Use `/team add <name> <role>` to add someone."},
        })
        return blocks

    for member in members:
        name = member.get("name", "Unknown")
        role = member.get("role", "")
        email = member.get("email", "")
        status = member.get("status", "active")

        status_icon = "🟢" if status == "active" else "⚪"
        text = f"{status_icon} *{name}* — {role}"
        if email:
            text += f"\n   📧 {email}"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

    return blocks

def _projects_block(data: dict) -> list:
    """Format projects list as Slack blocks."""
    projects = data.get("projects", [])

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 Active Projects", "emoji": True},
        },
        {"type": "divider"},
    ]

    if not projects:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "No active projects."},
        })
        return blocks

    for project in projects:
        name = project.get("name", "Unnamed")
        status = project.get("status", "active")
        assignee = project.get("assignee", {})
        if isinstance(assignee, dict):
            assignee_name = assignee.get("name", "Unassigned")
        else:
            assignee_name = str(assignee) if assignee else "Unassigned"
        due_date = project.get("due_date", "")
        description = project.get("description", "")

        text = f"{_status_emoji(status)} *{name}*"
        text += f"\n   👤 {assignee_name}"
        if due_date:
            text += f" | 📅 Due: {due_date[:10]}"
        if description:
            text += f"\n   {description[:100]}"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text},
        })

    return blocks

def _dashboard_block(data: dict) -> list:
    """Format the full team dashboard as Slack blocks."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📊 Regent Team Dashboard", "emoji": True},
        },
        {"type": "divider"},
    ]

    # Pipeline section
    pipeline = data.get("pipeline", {})
    if pipeline and "error" not in pipeline:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Pipeline*\n"
                    f"🆕 New: {pipeline.get('new_leads', 0)} | "
                    f"🔵 Contacted: {pipeline.get('contacted', 0)} | "
                    f"🟡 Follow-up: {pipeline.get('follow_up', 0)} | "
                    f"🟠 Interested: {pipeline.get('interested', 0)} | "
                    f"🟢 Closed: {pipeline.get('closed', 0)}\n"
                    f"📈 Conversion: {pipeline.get('conversion_rate', 0)}% | "
                    f"📬 Reply: {pipeline.get('reply_rate', 0)}%"
                ),
            },
        })
        blocks.append({"type": "divider"})

    # Active projects
    projects = data.get("active_projects", [])
    if projects:
        proj_text = "\n".join([
            f"  • {_status_emoji(p.get('status', ''))} *{p.get('name', '')}* — {p.get('assignee', {}).get('name', 'Unassigned')}"
            for p in projects[:5]
        ])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Active Projects:*\n{proj_text}"},
        })
        blocks.append({"type": "divider"})

    # Team members
    members = data.get("team_members", [])
    if members:
        member_text = "\n".join([
            f"  • {m.get('name', '')} — {m.get('role', '')}"
            for m in members
        ])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Team:*\n{member_text}"},
        })
        blocks.append({"type": "divider"})

    # Recent leads
    recent = data.get("recent_leads", [])
    if recent:
        recent_text = "\n".join([
            f"  • {r.get('name', '')} — {r.get('business', '')} ({_status_emoji(r.get('status', ''))})"
            for r in recent[:3]
        ])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Recent Leads:*\n{recent_text}"},
        })

    return blocks

# ── Command Handlers ────────────────────────────────────────────────────

async def handle_leads_command(text: str) -> tuple[str, Optional[list]]:
    """
    Handle /leads command.
    Usage: /leads [status] [--source X] [--limit N]
    """
    parts = text.strip().split()
    params = {"limit": "10"}
    subcommand = None

    # Parse simple args
    i = 0
    while i < len(parts):
        if parts[i] == "--source" and i + 1 < len(parts):
            params["source"] = parts[i + 1]
            i += 2
        elif parts[i] == "--limit" and i + 1 < len(parts):
            params["limit"] = parts[i + 1]
            i += 2
        elif parts[i] == "--status" and i + 1 < len(parts):
            params["status"] = parts[i + 1]
            i += 2
        elif parts[i] in ("new", "contacted", "follow-up", "interested", "closed"):
            params["status"] = parts[i]
            i += 1
        else:
            subcommand = parts[i]
            i += 1

    if subcommand == "summary" or not text.strip():
        # Get pipeline summary
        data = await _crm_api_get("/leads/summary")
        if "error" in data:
            return f"⚠️ {data['error']}", None
        return "", _pipeline_block(data)

    # Get leads list
    data = await _crm_api_get("/leads?" + "&".join(f"{k}={v}" for k, v in params.items()))
    if "error" in data:
        return f"⚠️ {data['error']}", None

    title = f"Leads — {params.get('status', 'all')}".title()
    return "", _leads_list_block(data, title=title)


async def handle_team_command(text: str) -> tuple[str, Optional[list]]:
    """
    Handle /team command.
    Usage: /team — list all members
           /team add <name> <role> [email]
    """
    parts = text.strip().split()

    if not text.strip():
        # List team
        data = await _crm_api_get("/team")
        if "error" in data:
            return f"⚠️ {data['error']}", None
        return "", _team_block(data)

    if parts[0] == "add" and len(parts) >= 3:
        name = parts[1]
        role = parts[2]
        email = parts[3] if len(parts) > 3 else None
        payload = {"name": name, "role": role}
        if email:
            payload["email"] = email
        result = await _crm_api_post("/team", payload)
        if "error" in result:
            return f"⚠️ Failed to add team member: {result['error']}", None
        return f"✅ Added *{name}* as {role} to the team.", None

    return (
        "Usage:\n"
        "  `/team` — list all members\n"
        "  `/team add <name> <role> [email]` — add a member",
        None,
    )


async def handle_projects_command(text: str) -> tuple[str, Optional[list]]:
    """
    Handle /projects command.
    Usage: /projects — list active projects
           /projects all — list all projects
           /projects add <name> [--assignee <name>] [--due <date>]
    """
    parts = text.strip().split()

    if not text.strip() or parts[0] == "active":
        data = await _crm_api_get("/projects?status=active")
        if "error" in data:
            return f"⚠️ {data['error']}", None
        return "", _projects_block(data)

    if parts[0] == "all":
        data = await _crm_api_get("/projects")
        if "error" in data:
            return f"⚠️ {data['error']}", None
        return "", _projects_block(data)

    if parts[0] == "add" and len(parts) >= 2:
        name = parts[1]
        payload = {"name": name, "status": "active"}
        # Parse optional flags
        i = 2
        while i < len(parts):
            if parts[i] == "--assignee" and i + 1 < len(parts):
                payload["assignee_id"] = parts[i + 1]
                i += 2
            elif parts[i] == "--due" and i + 1 < len(parts):
                payload["due_date"] = parts[i + 1]
                i += 2
            else:
                i += 1
        result = await _crm_api_post("/projects", payload)
        if "error" in result:
            return f"⚠️ Failed to create project: {result['error']}", None
        return f"✅ Created project *{name}*.", None

    return (
        "Usage:\n"
        "  `/projects` — list active projects\n"
        "  `/projects all` — list all projects\n"
        "  `/projects add <name> [--assignee <id>] [--due YYYY-MM-DD]`",
        None,
    )


async def handle_dashboard_command() -> tuple[str, Optional[list]]:
    """Handle /dashboard command — full team overview."""
    data = await _crm_api_get("/dashboard")
    if "error" in data:
        return f"⚠️ {data['error']}", None
    return "", _dashboard_block(data)


async def handle_pipeline_command() -> tuple[str, Optional[list]]:
    """Handle /pipeline command — just the funnel."""
    data = await _crm_api_get("/leads/summary")
    if "error" in data:
        return f"⚠️ {data['error']}", None
    return "", _pipeline_block(data)
