"""Autopilot notifications — in-app (alert_events), Slack and email, best-effort.

quiet runs never notify. A failure streak notifies once (the scheduler calls
this when it auto-pauses). Email goes through SMTP Settings directly, never the
approval-gated send_email tool.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


async def notify(
    job: Optional[dict],
    run_id: Optional[str],
    status: str,
    summary: Optional[str],
    reason: Optional[str] = None,
) -> None:
    if status == "quiet":
        return
    try:
        await _in_app(job, run_id, status, summary, reason)
    except Exception:
        logger.exception("[autopilot] in-app notify failed")
    config = (job or {}).get("notify") or {}
    slack_cfg = config.get("slack") if isinstance(config.get("slack"), dict) else None
    email_cfg = config.get("email") if isinstance(config.get("email"), dict) else None
    if slack_cfg and slack_cfg.get("enabled"):
        try:
            await _slack(slack_cfg, job, status, summary)
        except Exception:
            logger.exception("[autopilot] slack notify failed")
    if email_cfg and email_cfg.get("enabled") and email_cfg.get("to"):
        try:
            await _email(email_cfg, job, status, summary)
        except Exception:
            logger.exception("[autopilot] email notify failed")


async def _in_app(job, run_id, status, summary, reason) -> None:
    import db.client as db
    supabase = db.get_db()
    source = f"autopilot:{job.get('name') if job else '?'}"
    title = f"Autopilot run {status}"
    if job and job.get("name"):
        title = f"{job['name']} — {status}"
    message = summary or reason or ""
    severity = "critical" if status in ("failed", "budget_stopped") else "info"
    row = {"severity": severity, "title": title, "message": message[:2000], "source": source[:100]}
    if run_id:
        row["source_ref"] = run_id
    await db._async_execute(lambda: supabase.table("alert_events").insert(row).execute())


async def _slack(cfg: dict, job, status, summary) -> None:
    from slack_sdk import WebClient
    token = None
    try:
        from config import settings
        token = getattr(settings, "slack_bot_token", None)
    except Exception:
        token = None
    if not token:
        logger.warning("[autopilot] slack notify requested but SLACK_BOT_TOKEN unset")
        return
    client = WebClient(token=token)
    text = f"*Autopilot* {job.get('name') if job else ''} — {status}:\n{summary or ''}"[:3000]
    await _thread_safe_post(client, cfg.get("channel") or "ops", text)


async def _thread_safe_post(client, channel: str, text: str) -> None:
    import asyncio
    await asyncio.get_event_loop().run_in_executor(None, lambda: client.chat_postMessage(channel=channel, text=text))


async def _email(cfg: dict, job, status, summary) -> None:
    from config import settings
    host = getattr(settings, "smtp_host", None) or ""
    port = int(getattr(settings, "smtp_port", None) or 587)
    user = getattr(settings, "smtp_user", None) or ""
    password = getattr(settings, "smtp_password", None) or ""
    frm = getattr(settings, "smtp_from_email", None) or "dawn@regent.ug"
    if not (host and user and password):
        logger.warning("[autopilot] email notify requested but SMTP unset")
        return
    to = cfg.get("to") or ""
    subject = f"Autopilot: {job.get('name') if job else ''} — {status}"
    msg = MIMEText(summary or "", "plain")
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = to
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(frm, [a for a in to.split(",") if a.strip()], msg.as_string())
