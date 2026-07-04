"""
Background scheduler for automated pentest tasks.
Runs periodic LAN scans, port scans, and OSINT sweeps.
Stores results in SQLite for persistence.
"""
import asyncio
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DAWN_SCHEDULER_DB", "/var/lib/dawn/scheduler.db")


def get_db() -> sqlite3.Connection:
    """Get or create the scheduler database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    return conn


def _init_db(conn: sqlite3.Connection):
    """Initialize database schema."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            tool TEXT NOT NULL,
            args TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL DEFAULT 86400,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_run_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scan_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schedule_id INTEGER,
            tool TEXT NOT NULL,
            target TEXT,
            raw_output TEXT,
            parsed_data TEXT,
            success INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER,
            run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (schedule_id) REFERENCES schedules(id)
        );

        CREATE TABLE IF NOT EXISTS network_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            mac TEXT,
            vendor TEXT,
            hostname TEXT,
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ports TEXT,
            os_detection TEXT,
            notes TEXT,
            UNIQUE(ip)
        );
    """)
    conn.commit()


def get_default_schedules() -> list[dict]:
    """Return default schedules for first-time setup."""
    return [
        {
            "name": "Daily LAN Scan",
            "description": "Scan local network for new devices every 24 hours",
            "tool": "arp-scan",
            "args": "--localnet",
            "interval_seconds": 86400,
        },
        {
            "name": "Weekly Port Scan",
            "description": "Full port scan of known devices every 7 days",
            "tool": "nmap",
            "args": "-T4 -p- --open 192.168.1.0/24",
            "interval_seconds": 604800,
        },
    ]


def ensure_default_schedules():
    """Create default schedules if none exist."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
    if count == 0:
        for sched in get_default_schedules():
            conn.execute(
                """INSERT INTO schedules (name, description, tool, args, interval_seconds)
                   VALUES (?, ?, ?, ?, ?)""",
                (sched["name"], sched["description"], sched["tool"],
                 sched["args"], sched["interval_seconds"]),
            )
        conn.commit()
        logger.info("Created %d default schedules", len(get_default_schedules()))
    conn.close()


def get_due_schedules() -> list[sqlite3.Row]:
    """Get schedules that are due to run."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM schedules
           WHERE enabled = 1
           AND (last_run_at IS NULL
                OR (strftime('%%s', 'now') - strftime('%%s', last_run_at)) >= interval_seconds)"""
    ).fetchall()
    conn.close()
    return rows


def record_run(schedule_id: int, tool: str, target: str, output: str,
               success: bool, duration_ms: int, parsed: Optional[dict] = None):
    """Record a scan run result."""
    conn = get_db()
    conn.execute(
        """INSERT INTO scan_results (schedule_id, tool, target, raw_output, parsed_data, success, duration_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (schedule_id, tool, target, output[:100000],
         json.dumps(parsed) if parsed else None, int(success), duration_ms),
    )
    conn.execute(
        "UPDATE schedules SET last_run_at = CURRENT_TIMESTAMP WHERE id = ?",
        (schedule_id,),
    )
    conn.commit()
    conn.close()


def upsert_device(ip: str, mac: Optional[str] = None, vendor: Optional[str] = None,
                  hostname: Optional[str] = None, ports: Optional[str] = None,
                  os_detection: Optional[str] = None):
    """Add or update a network device record."""
    conn = get_db()
    existing = conn.execute("SELECT * FROM network_devices WHERE ip = ?", (ip,)).fetchone()
    if existing:
        updates = ["last_seen = CURRENT_TIMESTAMP"]
        if mac and not existing["mac"]:
            updates.append(f"mac = '{mac}'")
        if vendor and not existing["vendor"]:
            updates.append(f"vendor = '{vendor}'")
        if hostname and not existing["hostname"]:
            updates.append(f"hostname = '{hostname}'")
        if ports:
            updates.append(f"ports = '{ports}'")
        if os_detection:
            updates.append(f"os_detection = '{os_detection}'")
        conn.execute(f"UPDATE network_devices SET {', '.join(updates)} WHERE ip = ?", (ip,))
    else:
        conn.execute(
            """INSERT INTO network_devices (ip, mac, vendor, hostname, ports, os_detection)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ip, mac, vendor, hostname, ports, os_detection),
        )
    conn.commit()
    conn.close()


# ── Scheduler Engine ────────────────────────────────────────────────────────

class SchedulerEngine:
    """Background scheduler that runs pentest tasks on a loop."""

    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler loop."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        self._running = True
        ensure_default_schedules()
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started (check interval: %ds)", self.check_interval)

    async def stop(self):
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                due = get_due_schedules()
                for sched in due:
                    asyncio.create_task(self._execute_schedule(dict(sched)))
            except Exception as e:
                logger.error("Scheduler check failed: %s", e)
            await asyncio.sleep(self.check_interval)

    async def _execute_schedule(self, sched: dict):
        """Execute a single scheduled task."""
        tool = sched["tool"]
        args = sched["args"]
        start = time.monotonic()

        logger.info("Running scheduled task: %s (%s %s)", sched["name"], tool, args)

        try:
            proc = await asyncio.create_subprocess_exec(
                *[tool] + args.split(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            duration = int((time.monotonic() - start) * 1000)
            output = stdout.decode(errors="replace")
            success = proc.returncode == 0

            record_run(sched["id"], tool, args, output, success, duration)

            # Parse devices from arp-scan output
            if tool == "arp-scan":
                self._parse_arp_scan(output)

            logger.info("Scheduled task '%s' completed in %dms (success=%s)",
                        sched["name"], duration, success)
        except asyncio.TimeoutError:
            duration = int((time.monotonic() - start) * 1000)
            record_run(sched["id"], tool, args, "TIMEOUT", False, duration)
            logger.warning("Scheduled task '%s' timed out", sched["name"])
        except FileNotFoundError:
            logger.error("Tool '%s' not found for scheduled task '%s'", tool, sched["name"])
        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            record_run(sched["id"], tool, args, str(e), False, duration)
            logger.error("Scheduled task '%s' failed: %s", sched["name"], e)

    def _parse_arp_scan(self, output: str):
        """Parse arp-scan output and upsert devices."""
        for line in output.split("\n"):
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                ip = parts[0]
                mac = parts[1] if len(parts) > 1 else None
                vendor = parts[2] if len(parts) > 2 else None
                if ip and mac and re.match(r'^\d+\.\d+\.\d+\.\d+$', ip):
                    upsert_device(ip=ip, mac=mac, vendor=vendor)


# Singleton
_engine: Optional[SchedulerEngine] = None


def get_scheduler() -> SchedulerEngine:
    global _engine
    if _engine is None:
        _engine = SchedulerEngine()
    return _engine
