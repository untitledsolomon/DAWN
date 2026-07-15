"""
Migration Runner — runs SQL migrations on Supabase.

Usage:
  python scripts/run_migration.py migrations/009_team_and_projects.sql

Requires:
  - SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment
  - Or: psql connection string in SUPABASE_DATABASE_URL

This script tries multiple methods to run SQL:
  1. Direct psql (if SUPABASE_DATABASE_URL is set)
  2. Supabase Management API (if SUPABASE_ACCESS_TOKEN is set)
  3. Prints the SQL for manual execution in Supabase Dashboard
"""
import os
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def read_sql(path: str) -> str:
    with open(path) as f:
        return f.read()


def run_via_psql(sql: str) -> bool:
    """Run SQL via psql using DATABASE_URL."""
    db_url = os.environ.get("SUPABASE_DATABASE_URL")
    if not db_url:
        return False

    try:
        result = subprocess.run(
            ["psql", db_url],
            input=sql,
            text=True,
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            logger.info("Migration ran successfully via psql")
            return True
        else:
            logger.error(f"psql failed: {result.stderr[:500]}")
            return False
    except FileNotFoundError:
        logger.warning("psql not found")
        return False
    except Exception as e:
        logger.error(f"psql error: {e}")
        return False


def run_via_management_api(sql: str) -> bool:
    """Run SQL via Supabase Management API."""
    import httpx

    access_token = os.environ.get("SUPABASE_ACCESS_TOKEN")
    project_ref = os.environ.get("SUPABASE_PROJECT_REF")

    if not access_token or not project_ref:
        return False

    url = f"https://api.supabase.com/v1/projects/{project_ref}/sql"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, json={"query": sql}, headers=headers, timeout=30)
        if resp.status_code == 200:
            logger.info("Migration ran successfully via Management API")
            return True
        else:
            logger.error(f"Management API error: {resp.status_code} {resp.text[:300]}")
            return False
    except Exception as e:
        logger.error(f"Management API error: {e}")
        return False


def print_manual_instructions(sql: str, path: str):
    """Print instructions for manual execution."""
    project_ref = os.environ.get("SUPABASE_URL", "").replace("https://", "").split(".")[0]
    print("\n" + "=" * 60)
    print("MANUAL MIGRATION REQUIRED")
    print("=" * 60)
    print(f"\nTo run migration '{path}':")
    print(f"\n1. Go to: https://supabase.com/dashboard/project/{project_ref}/sql/new")
    print(f"\n2. Paste the following SQL and click 'Run':")
    print("\n" + "-" * 60)
    print(sql)
    print("-" * 60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_migration.py <sql_file>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    sql = read_sql(path)
    logger.info(f"Read migration: {path} ({len(sql)} chars)")

    # Try methods in order
    if run_via_psql(sql):
        return
    if run_via_management_api(sql):
        return

    # Fallback: print manual instructions
    print_manual_instructions(sql, path)
    sys.exit(1)


if __name__ == "__main__":
    main()
