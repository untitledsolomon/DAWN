"""
Control Center Supabase Client — connects to a separate Supabase project
that holds the jarvis_* tables (jarvis_tasks, jarvis_goals, jarvis_resources,
jarvis_notifications, jarvis_activity_log).

This keeps DAWN's own data in its own Supabase project and the Control
Center's operational data in its own project, avoiding any migration.
"""
from supabase import create_client, Client
from config import settings
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_cc_client: Optional[Client] = None


def get_cc_db() -> Client:
    """Get or create the Control Center Supabase client.

    Uses cc_supabase_url and cc_supabase_service_key from settings.
    Falls back to the main DAWN Supabase client if CC vars are not set
    (for backward compatibility during local dev).
    """
    global _cc_client
    if _cc_client is None:
        if settings.cc_supabase_url and settings.cc_supabase_service_key:
            _cc_client = create_client(
                settings.cc_supabase_url,
                settings.cc_supabase_service_key,
            )
            logger.info(
                f"Control Center Supabase client initialized: {settings.cc_supabase_url}"
            )
        else:
            # Fallback: use the main DAWN Supabase client
            # This happens when CC env vars aren't set (local dev, testing)
            from db.client import get_db
            logger.warning(
                "CC_SUPABASE_URL not set — falling back to main DAWN Supabase client"
            )
            return get_db()
    return _cc_client
