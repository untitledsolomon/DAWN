"""
Auto-migration script — runs pending migrations against DAWN's Supabase
via the REST API (Data API). Called on DAWN startup.

Uses the service_role key to bypass RLS and create tables/functions.
"""
import os
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Track which migrations have been run in a metadata table
METADATA_TABLE = "_migrations"


async def get_headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SERVICE_KEY}",
        "apikey": SERVICE_KEY,
    }


async def ensure_metadata_table(client: httpx.AsyncClient):
    """Create the _migrations tracking table if it doesn't exist."""
    headers = await get_headers()
    # Try to query it — if 404, create it via the REST API
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/{METADATA_TABLE}?limit=1",
        headers=headers,
    )
    if resp.status_code == 404:
        # Table doesn't exist — we can't create it via REST API without raw SQL.
        # Instead, we'll use a file-based tracking mechanism.
        return False
    return True


def get_run_migrations() -> set:
    """Get list of already-run migrations from a local file."""
    tracking_file = Path(MIGRATIONS_DIR) / ".run_migrations"
    if tracking_file.exists():
        return set(tracking_file.read_text().strip().split("\n"))
    return set()


def mark_migration_run(name: str):
    """Mark a migration as run."""
    tracking_file = Path(MIGRATIONS_DIR) / ".run_migrations"
    run = get_run_migrations()
    run.add(name)
    tracking_file.write_text("\n".join(sorted(run)))


async def run_migration_via_sql_endpoint(client: httpx.AsyncClient, sql: str) -> bool:
    """
    Try to run SQL via the Supabase SQL endpoint.
    Some projects have /rest/v1/sql or /rest/v1/rpc/ available.
    """
    headers = await get_headers()

    # Method 1: Try /rest/v1/sql (PostgREST SQL endpoint)
    resp = await client.post(
        f"{SUPABASE_URL}/rest/v1/sql",
        headers=headers,
        json={"query": sql},
    )
    if resp.status_code < 400:
        logger.info(f"SQL via /rest/v1/sql succeeded: {resp.status_code}")
        return True

    # Method 2: Try as a raw query via the Data API
    # Split SQL into individual statements and try to create tables
    # by inserting a row (which auto-creates if the table doesn't exist? No.)
    logger.warning(f"SQL endpoint returned {resp.status_code}: {resp.text[:200]}")
    return False


async def run_migration_via_management_api(sql: str) -> bool:
    """
    Try to run SQL via the Supabase Management API.
    Requires a SUPABASE_ACCESS_TOKEN (PAT) environment variable.
    """
    access_token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    if not access_token:
        logger.info("No SUPABASE_ACCESS_TOKEN set — skipping Management API")
        return False

    project_ref = SUPABASE_URL.replace("https://", "").split(".")[0]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.supabase.com/v1/projects/{project_ref}/database/query",
            headers=headers,
            json={"query": sql},
        )
        if resp.status_code < 400:
            logger.info(f"Management API succeeded: {resp.status_code}")
            return True
        logger.warning(f"Management API returned {resp.status_code}: {resp.text[:200]}")
        return False


async def run_all_pending():
    """Run all pending migrations."""
    if not SUPABASE_URL or not SERVICE_KEY:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_KEY not set — skipping migrations")
        return

    run_migrations = get_run_migrations()
    migration_files = sorted(Path(MIGRATIONS_DIR).glob("*.sql"))

    for mig_file in migration_files:
        if mig_file.name in run_migrations:
            logger.info(f"Migration {mig_file.name} already run — skipping")
            continue

        sql = mig_file.read_text()
        logger.info(f"Running migration: {mig_file.name}")

        # Try Management API first (needs SUPABASE_ACCESS_TOKEN)
        success = await run_migration_via_management_api(sql)

        # Fall back to SQL endpoint
        if not success:
            async with httpx.AsyncClient() as client:
                success = await run_migration_via_sql_endpoint(client, sql)

        if success:
            mark_migration_run(mig_file.name)
            logger.info(f"Migration {mig_file.name} completed")
        else:
            logger.warning(
                f"Migration {mig_file.name} could not be run automatically. "
                f"Run it manually in the Supabase SQL Editor."
            )


if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_all_pending())
