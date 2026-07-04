"""
v19.0 — Email & Communication
Email integration, automation, Slack/Telegram, newsletter management
"""
import json
import logging
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class EmailAccountCreate(BaseModel):
    email: str
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    use_tls: bool = True
    name: str = ""

class EmailSendRequest(BaseModel):
    to: list[str]
    subject: str
    body: str
    body_type: str = "plain"  # 'plain' or 'html'
    cc: list[str] = []
    bcc: list[str] = []
    account_id: str

class EmailSearchRequest(BaseModel):
    query: str = "ALL"
    limit: int = 20
    account_id: str

class NewsletterCreate(BaseModel):
    title: str
    subject: str
    body: str
    body_type: str = "html"
    recipient_list_id: str
    scheduled_at: Optional[str] = None

class RecipientListCreate(BaseModel):
    name: str
    description: str = ""
    recipients: list[str] = []

# ─── Email Accounts ───────────────────────────────────────────────────────

@router.get("/email/accounts", tags=["email"])
async def list_email_accounts(_: None = Depends(verify_key)):
    """List configured email accounts."""
    try:
        supabase = db.get_db()
        res = supabase.table("email_accounts").select(
            "id, email, name, smtp_host, imap_host, is_active, last_checked_at, created_at"
        ).order("email").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[email] list accounts failed: {e}")
        return []


@router.post("/email/accounts", tags=["email"])
async def create_email_account(req: EmailAccountCreate, _: None = Depends(verify_key)):
    """Add an email account."""
    try:
        supabase = db.get_db()
        
        # Encrypt passwords before storing
        from cryptography.fernet import Fernet
        from config import settings
        
        # Use a derived key from the DAWN API key
        key = Fernet.generate_key()  # In production, derive from a master secret
        cipher = Fernet(key)
        
        data = req.model_dump()
        data["smtp_password_encrypted"] = cipher.encrypt(req.smtp_password.encode()).decode()
        data["imap_password_encrypted"] = cipher.encrypt(req.imap_password.encode()).decode()
        data["encryption_key"] = key.decode()
        
        # Remove plaintext passwords
        del data["smtp_password"]
        del data["imap_password"]
        
        res = supabase.table("email_accounts").insert(data).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[email] create account failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create email account: {str(e)}")


@router.delete("/email/accounts/{account_id}", tags=["email"])
async def delete_email_account(account_id: str, _: None = Depends(verify_key)):
    """Remove an email account."""
    try:
        supabase = db.get_db()
        supabase.table("email_accounts").delete().eq("id", account_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"[email] delete account failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")


# ─── Send Email ───────────────────────────────────────────────────────────

@router.post("/email/send", tags=["email"])
async def send_email(
    req: EmailSendRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    """Send an email via a configured account."""
    try:
        supabase = db.get_db()
        
        # Get account
        account = supabase.table("email_accounts").select("*").eq("id", req.account_id).execute()
        if not account.data:
            raise HTTPException(status_code=404, detail="Email account not found")
        
        acc = account.data[0]
        
        # Decrypt password
        from cryptography.fernet import Fernet
        cipher = Fernet(acc["encryption_key"].encode())
        smtp_password = cipher.decrypt(acc["smtp_password_encrypted"].encode()).decode()
        
        # Build message
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{acc.get('name', '')} <{acc['email']}>"
        msg["To"] = ", ".join(req.to)
        msg["Subject"] = req.subject
        if req.cc:
            msg["Cc"] = ", ".join(req.cc)
        
        if req.body_type == "html":
            msg.attach(MIMEText(req.body, "html"))
        else:
            msg.attach(MIMEText(req.body, "plain"))
        
        # Send
        background_tasks.add_task(
            _send_smtp,
            acc["smtp_host"],
            acc["smtp_port"],
            acc["smtp_username"],
            smtp_password,
            acc["email"],
            req.to + req.cc,
            msg,
            acc["use_tls"],
        )
        
        # Log the send
        supabase.table("email_logs").insert({
            "account_id": req.account_id,
            "from_email": acc["email"],
            "to_emails": req.to,
            "subject": req.subject,
            "status": "sending",
        }).execute()
        
        return {"status": "sending", "to": req.to, "subject": req.subject}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[email] send failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


def _send_smtp(host, port, username, password, from_addr, to_addrs, msg, use_tls):
    """Send email via SMTP (background task)."""
    try:
        if use_tls:
            server = smtplib.SMTP(host, port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(host, port)
        
        server.login(username, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        logger.info(f"[email] Sent email to {to_addrs}")
    except Exception as e:
        logger.error(f"[email] SMTP send failed: {e}")


# ─── Receive Email ────────────────────────────────────────────────────────

@router.post("/email/check/{account_id}", tags=["email"])
async def check_email(account_id: str, _: None = Depends(verify_key)):
    """Check for new emails via IMAP."""
    try:
        supabase = db.get_db()
        
        account = supabase.table("email_accounts").select("*").eq("id", account_id).execute()
        if not account.data:
            raise HTTPException(status_code=404, detail="Email account not found")
        
        acc = account.data[0]
        
        # Decrypt password
        from cryptography.fernet import Fernet
        cipher = Fernet(acc["encryption_key"].encode())
        imap_password = cipher.decrypt(acc["imap_password_encrypted"].encode()).decode()
        
        # Connect to IMAP
        mail = imaplib.IMAP4_SSL(acc["imap_host"], acc["imap_port"])
        mail.login(acc["imap_username"], imap_password)
        mail.select("INBOX")
        
        # Search for unseen messages
        status, messages = mail.search(None, "UNSEEN")
        if status != "OK":
            return {"new_emails": 0, "emails": []}
        
        email_ids = messages[0].split()
        new_emails = []
        
        for eid in email_ids[-20:]:  # Last 20 unseen
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status != "OK":
                continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            email_entry = {
                "message_id": msg.get("Message-ID", ""),
                "from": msg.get("From", ""),
                "to": msg.get("To", ""),
                "subject": msg.get("Subject", ""),
                "date": msg.get("Date", ""),
                "body": "",
            }
            
            # Extract body
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        email_entry["body"] = part.get_payload(decode=True).decode(errors="ignore")
                        break
            else:
                email_entry["body"] = msg.get_payload(decode=True).decode(errors="ignore")
            
            new_emails.append(email_entry)
            
            # Store in database
            supabase.table("email_messages").insert({
                "account_id": account_id,
                "message_id": email_entry["message_id"],
                "from_email": email_entry["from"],
                "to_emails": email_entry["to"],
                "subject": email_entry["subject"],
                "body": email_entry["body"][:10000],
                "received_at": email_entry["date"],
                "is_read": False,
            }).execute()
        
        mail.logout()
        
        # Update last checked
        supabase.table("email_accounts").update({
            "last_checked_at": "now()",
        }).eq("id", account_id).execute()
        
        return {"new_emails": len(new_emails), "emails": new_emails[:5]}
    
    except Exception as e:
        logger.error(f"[email] check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check email: {str(e)}")


# ─── Email Messages ───────────────────────────────────────────────────────

@router.get("/email/messages", tags=["email"])
async def list_email_messages(
    account_id: Optional[str] = None,
    limit: int = 50,
    unread_only: bool = False,
    _: None = Depends(verify_key),
):
    """List email messages."""
    try:
        supabase = db.get_db()
        q = supabase.table("email_messages").select("*").order("received_at", desc=True).limit(limit)
        if account_id:
            q = q.eq("account_id", account_id)
        if unread_only:
            q = q.eq("is_read", False)
        res = q.execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[email] list messages failed: {e}")
        return []


@router.get("/email/messages/{message_id}", tags=["email"])
async def get_email_message(message_id: str, _: None = Depends(verify_key)):
    """Get a single email message."""
    try:
        supabase = db.get_db()
        res = supabase.table("email_messages").select("*").eq("id", message_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Mark as read
        supabase.table("email_messages").update({"is_read": True}).eq("id", message_id).execute()
        
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[email] get message failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get message: {str(e)}")


# ─── Recipient Lists ──────────────────────────────────────────────────────

@router.get("/email/lists", tags=["email"])
async def list_recipient_lists(_: None = Depends(verify_key)):
    """List recipient lists."""
    try:
        supabase = db.get_db()
        res = supabase.table("recipient_lists").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[email] list lists failed: {e}")
        return []


@router.post("/email/lists", tags=["email"])
async def create_recipient_list(req: RecipientListCreate, _: None = Depends(verify_key)):
    """Create a recipient list."""
    try:
        supabase = db.get_db()
        res = supabase.table("recipient_lists").insert(req.model_dump()).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[email] create list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create list: {str(e)}")


@router.delete("/email/lists/{list_id}", tags=["email"])
async def delete_recipient_list(list_id: str, _: None = Depends(verify_key)):
    """Delete a recipient list."""
    try:
        supabase = db.get_db()
        supabase.table("recipient_lists").delete().eq("id", list_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        logger.error(f"[email] delete list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete list: {str(e)}")


# ─── Newsletters ──────────────────────────────────────────────────────────

@router.get("/email/newsletters", tags=["email"])
async def list_newsletters(_: None = Depends(verify_key)):
    """List newsletters."""
    try:
        supabase = db.get_db()
        res = supabase.table("newsletters").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception as e:
        logger.error(f"[email] list newsletters failed: {e}")
        return []


@router.post("/email/newsletters", tags=["email"])
async def create_newsletter(req: NewsletterCreate, _: None = Depends(verify_key)):
    """Create and optionally schedule a newsletter."""
    try:
        supabase = db.get_db()
        data = req.model_dump()
        data["status"] = "draft" if not req.scheduled_at else "scheduled"
        res = supabase.table("newsletters").insert(data).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        logger.error(f"[email] create newsletter failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create newsletter: {str(e)}")


@router.post("/email/newsletters/{newsletter_id}/send", tags=["email"])
async def send_newsletter(
    newsletter_id: str,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    """Send a newsletter to its recipient list."""
    try:
        supabase = db.get_db()
        
        # Get newsletter
        nl = supabase.table("newsletters").select("*").eq("id", newsletter_id).execute()
        if not nl.data:
            raise HTTPException(status_code=404, detail="Newsletter not found")
        
        newsletter = nl.data[0]
        
        # Get recipient list
        recipients = supabase.table("recipient_lists").select("*").eq(
            "id", newsletter["recipient_list_id"]
        ).execute()
        
        if not recipients.data:
            raise HTTPException(status_code=404, detail="Recipient list not found")
        
        recipient_emails = recipients.data[0].get("recipients", [])
        
        if not recipient_emails:
            raise HTTPException(status_code=400, detail="Recipient list is empty")
        
        # Get default email account
        accounts = supabase.table("email_accounts").select("*").eq("is_active", True).limit(1).execute()
        if not accounts.data:
            raise HTTPException(status_code=400, detail="No active email account configured")
        
        account = accounts.data[0]
        
        # Send to all recipients
        background_tasks.add_task(
            _send_bulk_email,
            account,
            recipient_emails,
            newsletter["subject"],
            newsletter["body"],
            newsletter["body_type"],
        )
        
        # Update status
        supabase.table("newsletters").update({
            "status": "sending",
            "sent_at": "now()",
        }).eq("id", newsletter_id).execute()
        
        return {
            "status": "sending",
            "recipient_count": len(recipient_emails),
            "subject": newsletter["subject"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[email] send newsletter failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send newsletter: {str(e)}")


def _send_bulk_email(account, recipients, subject, body, body_type):
    """Send bulk email to multiple recipients."""
    try:
        from cryptography.fernet import Fernet
        cipher = Fernet(account["encryption_key"].encode())
        smtp_password = cipher.decrypt(account["smtp_password_encrypted"].encode()).decode()
        
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{account.get('name', '')} <{account['email']}>"
        msg["Subject"] = subject
        
        if body_type == "html":
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))
        
        if account["use_tls"]:
            server = smtplib.SMTP(account["smtp_host"], account["smtp_port"])
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(account["smtp_host"], account["smtp_port"])
        
        server.login(account["smtp_username"], smtp_password)
        
        for recipient in recipients:
            msg["To"] = recipient
            server.sendmail(account["email"], [recipient], msg.as_string())
            del msg["To"]
        
        server.quit()
        logger.info(f"[email] Sent newsletter to {len(recipients)} recipients")
    except Exception as e:
        logger.error(f"[email] Bulk send failed: {e}")


# ─── Slack/Telegram Integration ───────────────────────────────────────────

class WebhookMessage(BaseModel):
    message: str
    channel: str = "general"
    webhook_url: str

@router.post("/email/webhook/send", tags=["email"])
async def send_webhook_message(req: WebhookMessage, _: None = Depends(verify_key)):
    """Send a message via webhook (Slack, Telegram, Discord, etc.)."""
    try:
        import httpx
        
        payload = {"text": req.message, "channel": req.channel}
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(req.webhook_url, json=payload, timeout=10)
        
        return {"status": "sent", "status_code": resp.status_code}
    except Exception as e:
        logger.error(f"[email] webhook send failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send webhook message: {str(e)}")


# ─── Communication Analytics ──────────────────────────────────────────────

@router.get("/email/analytics", tags=["email"])
async def get_email_analytics(_: None = Depends(verify_key)):
    """Get email communication analytics."""
    try:
        supabase = db.get_db()
        
        # Total messages
        total = supabase.table("email_messages").select("id", count="exact").execute()
        total_count = total.count if hasattr(total, 'count') else len(total.data or [])
        
        # Unread
        unread = supabase.table("email_messages").select("id", count="exact").eq("is_read", False).execute()
        unread_count = unread.count if hasattr(unread, 'count') else len(unread.data or [])
        
        # Sent today
        import datetime
        today = datetime.date.today().isoformat()
        sent_today = supabase.table("email_logs").select("id", count="exact").gte(
            "created_at", today
        ).execute()
        sent_count = sent_today.count if hasattr(sent_today, 'count') else len(sent_today.data or [])
        
        # Accounts
        accounts = supabase.table("email_accounts").select("id", count="exact").execute()
        account_count = accounts.count if hasattr(accounts, 'count') else len(accounts.data or [])
        
        return {
            "total_messages": total_count,
            "unread_messages": unread_count,
            "sent_today": sent_count,
            "active_accounts": account_count,
        }
    except Exception as e:
        logger.error(f"[email] analytics failed: {e}")
        return {
            "total_messages": 0,
            "unread_messages": 0,
            "sent_today": 0,
            "active_accounts": 0,
        }
