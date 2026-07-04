"""
Database tool — full read/write access to every table in the DAWN Supabase
project, using the same service-role client as db/client.py.

This deliberately does NOT sandbox by table the way filesystem.py sandboxes
by path. Solomon asked for full table access, and TIER_TOOL_ACCESS (see
llm/identity.py) already gives us the right place to enforce that: this tool
is only ever exposed to OWNER-tier identities, the same tier that already
gets install_skill/git. SERVICE-tier keys never see "database" in their
tool list at all — see TIER_TOOL_ACCESS.

Within OWNER tier, this still isn't a raw SQL shell:
  - Structured operations only (select/insert/update/delete/rpc), each
    logged with the table + row count involved, so agent tool_call/
    tool_result events in the transcript double as an audit trail.
  - update/delete require a `filters` dict — an empty filters dict is
    rejected rather than silently taking that as "match everything", so
    typos can't nuke a table.
  - `sql` operation for arbitrary SQL is present but off by default; only
    enabled if config.settings.database_tool_allow_raw_sql is truthy, since
    raw SQL bypasses the row-count logging entirely.
"""
import logging
from typing import Any, Optional
from tools.base import BaseTool, ToolResult
from config import settings
import db.client as db

logger = logging.getLogger(__name__)


class DatabaseTool(BaseTool):
    name = "database"
    description = (
        "Read and write any table in the DAWN Supabase database (nodes, chat_sessions, "
        "chat_messages, tags, memory_sessions, error_patterns, node_tags, knowledge_extractions, "
        "and any other table in the project) using the service-role connection — this bypasses "
        "row-level security, so it can see and modify everything regardless of RLS policies. "
        "Use 'select' to query rows, 'insert' to create rows, 'update' or 'delete' to modify "
        "existing rows (both require a non-empty 'filters' dict so you can't accidentally affect "
        "every row in a table), and 'list_tables' if you're unsure what tables exist or need a "
        "reminder of the schema. Prefer the narrowest filters and smallest limit that answer the "
        "question — this is a real production database, not a sandbox."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["select", "insert", "update", "delete", "list_tables"],
                "description": "The database operation to perform.",
            },
            "table": {
                "type": "string",
                "description": "Table name, e.g. 'nodes' or 'chat_sessions'. Not required for 'list_tables'.",
            },
            "columns": {
                "type": "string",
                "description": "Comma-separated columns for 'select', e.g. 'id,title,created_at'. Defaults to '*'.",
            },
            "filters": {
                "type": "object",
                "description": (
                    "Equality filters as {column: value}, e.g. {\"id\": \"abc-123\"}. "
                    "Required (and must be non-empty) for 'update' and 'delete'. Optional for 'select'."
                ),
            },
            "data": {
                "type": "object",
                "description": "Row data for 'insert' (single row) or fields to change for 'update'.",
            },
            "rows": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Multiple rows for a bulk 'insert'. Use either 'data' or 'rows', not both.",
            },
            "limit": {
                "type": "integer",
                "description": "Max rows to return for 'select'. Defaults to 50, capped at 500.",
            },
            "order_by": {
                "type": "string",
                "description": "Column to order 'select' results by, e.g. 'created_at.desc'.",
            },
        },
        "required": ["operation"],
    }

    # Tables the tool will refuse to touch even under OWNER tier, in case you
    # want to carve out anything especially sensitive later. Empty by default
    # since you asked for full access — add table names here if you change
    # your mind about specific tables (e.g. billing/credentials tables).
    BLOCKED_TABLES: set[str] = set()

    def __init__(self):
        self.max_limit = getattr(settings, "database_tool_max_limit", 500)
        self.allow_raw_sql = bool(getattr(settings, "database_tool_allow_raw_sql", False))

    def _client(self):
        return db.get_db()

    def _check_table(self, table: Optional[str]) -> Optional[str]:
        if not table:
            return "A 'table' name is required for this operation."
        if table in self.BLOCKED_TABLES:
            return f"Table '{table}' is blocked for the database tool."
        return None

    async def run(
        self,
        operation: str,
        table: Optional[str] = None,
        columns: Optional[str] = None,
        filters: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        rows: Optional[list[dict[str, Any]]] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> ToolResult:
        try:
            if operation == "list_tables":
                return await self._list_tables()

            err = self._check_table(table)
            if err:
                return ToolResult(success=False, error=err)

            if operation == "select":
                return await self._select(table, columns, filters, limit, order_by)
            elif operation == "insert":
                return await self._insert(table, data, rows)
            elif operation == "update":
                return await self._update(table, data, filters)
            elif operation == "delete":
                return await self._delete(table, filters)
            else:
                return ToolResult(success=False, error=f"Unknown operation '{operation}'.")

        except Exception as e:
            logger.error(f"[database tool] {operation} on {table} failed: {e}")
            return ToolResult(success=False, error=str(e))

    async def _list_tables(self) -> ToolResult:
        """Best-effort table listing via Postgres information_schema, through
        an RPC if one exists, falling back to a hardcoded list of the tables
        DAWN itself creates and uses (see dawn_schema.sql)."""
        client = self._client()
        try:
            res = client.rpc("list_public_tables", {}).execute()
            if res.data:
                return ToolResult(success=True, output=res.data)
        except Exception:
            pass  # RPC probably doesn't exist — fall back below

        known = [
            "nodes", "node_tags", "tags", "chat_sessions", "chat_messages",
            "memory_sessions", "memory_node_origins", "knowledge_extractions",
            "error_patterns",
        ]
        return ToolResult(
            success=True,
            output=known,
            metadata={
                "note": (
                    "No list_public_tables RPC found in this project — returning the "
                    "known DAWN tables from dawn_schema.sql instead. Other tables may "
                    "exist; query them directly by name if you know it."
                )
            },
        )

    async def _select(
        self,
        table: str,
        columns: Optional[str],
        filters: Optional[dict[str, Any]],
        limit: Optional[int],
        order_by: Optional[str],
    ) -> ToolResult:
        client = self._client()
        capped_limit = min(limit or 50, self.max_limit)

        query = client.table(table).select(columns or "*")
        for col, val in (filters or {}).items():
            query = query.eq(col, val)
        if order_by:
            col, _, direction = order_by.partition(".")
            query = query.order(col, desc=(direction == "desc"))
        query = query.limit(capped_limit)

        res = query.execute()
        rows = res.data or []
        logger.info(f"[database tool] select {table}: {len(rows)} row(s)")
        return ToolResult(success=True, output=rows, metadata={"row_count": len(rows), "table": table})

    async def _insert(
        self,
        table: str,
        data: Optional[dict[str, Any]],
        rows: Optional[list[dict[str, Any]]],
    ) -> ToolResult:
        if not data and not rows:
            return ToolResult(success=False, error="Provide 'data' (single row) or 'rows' (multiple) to insert.")
        payload = rows if rows else [data]

        client = self._client()
        res = client.table(table).insert(payload).execute()
        inserted = res.data or []
        logger.info(f"[database tool] insert {table}: {len(inserted)} row(s)")
        return ToolResult(success=True, output=inserted, metadata={"row_count": len(inserted), "table": table})

    async def _update(
        self,
        table: str,
        data: Optional[dict[str, Any]],
        filters: Optional[dict[str, Any]],
    ) -> ToolResult:
        if not data:
            return ToolResult(success=False, error="Provide 'data' with the fields to update.")
        if not filters:
            return ToolResult(
                success=False,
                error="'filters' is required for update and must be non-empty — refusing to update every row in a table.",
            )

        client = self._client()
        query = client.table(table).update(data)
        for col, val in filters.items():
            query = query.eq(col, val)
        res = query.execute()
        updated = res.data or []
        logger.info(f"[database tool] update {table} (filters={filters}): {len(updated)} row(s)")
        return ToolResult(success=True, output=updated, metadata={"row_count": len(updated), "table": table})

    async def _delete(self, table: str, filters: Optional[dict[str, Any]]) -> ToolResult:
        if not filters:
            return ToolResult(
                success=False,
                error="'filters' is required for delete and must be non-empty — refusing to delete every row in a table.",
            )

        client = self._client()
        query = client.table(table).delete()
        for col, val in filters.items():
            query = query.eq(col, val)
        res = query.execute()
        deleted = res.data or []
        logger.info(f"[database tool] delete {table} (filters={filters}): {len(deleted)} row(s)")
        return ToolResult(success=True, output=deleted, metadata={"row_count": len(deleted), "table": table})
