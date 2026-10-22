"""
Email Tool — send emails via SMTP.

Configure via SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
and SMTP_FROM_EMAIL environment variables.

Operations:
  - send_email: Send a plain text or HTML email
  - email_status: Check if SMTP is configured
"""

import logging
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

# SMTP is read from config.Settings (env-backed) so the Settings page's "env"
# badge is truthful — not a second copy of os.environ read at import.
SMTP_HOST = getattr(settings, "smtp_host", None) or ""
SMTP_PORT = int(getattr(settings, "smtp_port", None) or 587)
SMTP_USER = getattr(settings, "smtp_user", None) or ""
SMTP_PASSWORD = getattr(settings, "smtp_password", None) or ""
SMTP_FROM_EMAIL = getattr(settings, "smtp_from_email", None) or "dawn@regent.ug"


def _smtp_configured() -> bool:
    """Check if SMTP is configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


class EmailSendTool(BaseTool):
    """Send emails via SMTP."""

    name = "send_email"
    risk = "external_write"
    # Sending email is a mutating action on real communications — gate behind
    # human approval via the pending_actions queue.
    is_mutating = True
    description = (
        "Send an email via SMTP. Supports plain text and HTML content. "
        "Use for sending notifications, reports, invoices, or any email communications."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "Recipient email address(es). Comma-separated for multiple.",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line.",
            },
            "body": {
                "type": "string",
                "description": "Email body content. Plain text by default.",
            },
            "html": {
                "type": "boolean",
                "description": "Set to true if body contains HTML. Default: false.",
            },
            "cc": {
                "type": "string",
                "description": "CC recipient email address(es). Comma-separated. Optional.",
            },
        },
        "required": ["to", "subject", "body"],
    }

    async def run(self, **kwargs) -> ToolResult:
        to = kwargs.get("to", "")
        subject = kwargs.get("subject", "")
        body = kwargs.get("body", "")
        is_html = kwargs.get("html", False)
        cc = kwargs.get("cc", "")

        if not _smtp_configured():
            return ToolResult(
                success=False,
                error=(
                    "SMTP not configured. Set SMTP_HOST, SMTP_USER, and SMTP_PASSWORD "
                    "environment variables."
                ),
            )

        if not to or not subject or not body:
            return ToolResult(
                success=False,
                error="'to', 'subject', and 'body' are all required.",
            )

        try:
            msg = MIMEMultipart("alternative")
            msg["From"] = SMTP_FROM_EMAIL
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            # Attach plain text and optionally HTML
            msg.attach(MIMEText(body, "plain"))
            if is_html:
                msg.attach(MIMEText(body, "html"))

            # Build recipient list
            all_recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
            if cc:
                all_recipients.extend([addr.strip() for addr in cc.split(",") if addr.strip()])

            # Send via SMTP
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.sendmail(SMTP_FROM_EMAIL, all_recipients, msg.as_string())

            logger.info(f"Email sent to {to}: '{subject}'")
            return ToolResult(
                success=True,
                output={
                    "to": to,
                    "subject": subject,
                    "cc": cc or None,
                    "recipients": len(all_recipients),
                    "status": "sent",
                },
            )

        except smtplib.SMTPAuthenticationError:
            return ToolResult(
                success=False,
                error="SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD.",
            )
        except smtplib.SMTPException as e:
            return ToolResult(success=False, error=f"SMTP error: {e}")
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return ToolResult(success=False, error=str(e))


class EmailStatusTool(BaseTool):
    """Check if email/SMTP is configured."""

    name = "email_status"
    risk = "read"
    description = "Check if email/SMTP is configured and ready to send."
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def run(self, **kwargs) -> ToolResult:
        configured = _smtp_configured()
        return ToolResult(
            success=True,
            output={
                "configured": configured,
                "host": SMTP_HOST if configured else None,
                "from_email": SMTP_FROM_EMAIL,
                "message": "SMTP is configured and ready." if configured else "SMTP is not configured.",
            },
        )
