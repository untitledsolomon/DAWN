"""
Write-gating — approval queue for mutating tool calls.

Every mutating action (MCP tools with a create_/delete_/send_/publish_/update_
prefix, and native DAWN tools marked `is_mutating`) is queued in the
`pending_actions` table and requires human approval before it executes. This
is the safety gate that makes DAWN's "mutating actions always require
approval" hard requirement real.

Tool-source-agnostic: `server_id` is null for native tools and set for
MCP-routed calls, so one queue covers both paths.
"""
import logging
from typing import Awaitable, Callable, Optional

from tools.base import ToolResult

logger = logging.getLogger(__name__)

# Executors for an approved action: given (server_id, tool_name, args), run the
# action and return a ToolResult. MCP-routed actions (server_id set) use the
# MCP executor; native actions (server_id null) use the native executor.
_mcp_executor: Optional[Callable[[str, str, dict], Awaitable[ToolResult]]] = None
_native_executor: Optional[Callable[[str, dict], Awaitable[ToolResult]]] = None


def register_mcp_executor(fn: Callable[[str, str, dict], Awaitable[ToolResult]]) -> None:
    """Register the executor for approved MCP-routed actions (server_id set)."""
    global _mcp_executor
    _mcp_executor = fn


def register_native_executor(fn: Callable[[str, dict], Awaitable[ToolResult]]) -> None:
    """Register the executor for approved native-tool actions (server_id null)."""
    global _native_executor
    _native_executor = fn


async def execute_pending_action(action_id: str, resolved_by: Optional[str] = None) -> dict:
    """Execute an approved pending action and record the outcome.

    Loads the row, confirms it is `approved`, runs it through the registered
    executor, and updates the row to `completed`/`failed` with the result.
    Returns a summary dict.
    """
    import db.client as db
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("pending_actions").select(
        "*"
    ).eq("id", action_id).maybe_single().execute())
    row = res.data if res and res.data else None
    if not row:
        raise ValueError(f"Pending action {action_id} not found")
    if row.get("status") != "approved":
        raise ValueError(f"Action {action_id} is not in 'approved' state (status={row.get('status')})")

    server_id = row.get("server_id")
    tool_name = row.get("tool_name")
    tool_args = row.get("tool_args") or {}

    if server_id:
        if _mcp_executor is None:
            raise RuntimeError("No MCP approved-action executor registered")
        try:
            result = await _mcp_executor(server_id, tool_name, tool_args)
        except Exception as e:
            logger.exception(f"Approved action {action_id} failed to execute")
            await db._async_execute(lambda: supabase.table("pending_actions").update({
                "status": "failed",
                "error": str(e),
                "resolved_at": "now()",
                "resolved_by": resolved_by,
            }).eq("id", action_id).execute())
            return {"status": "failed", "error": str(e)}
    else:
        if _native_executor is None:
            raise RuntimeError("No native approved-action executor registered")
        try:
            result = await _native_executor(tool_name, tool_args)
        except Exception as e:
            logger.exception(f"Approved action {action_id} failed to execute")
            await db._async_execute(lambda: supabase.table("pending_actions").update({
                "status": "failed",
                "error": str(e),
                "resolved_at": "now()",
                "resolved_by": resolved_by,
            }).eq("id", action_id).execute())
            return {"status": "failed", "error": str(e)}
        logger.exception(f"Approved action {action_id} failed to execute")
        await db._async_execute(lambda: supabase.table("pending_actions").update({
            "status": "failed",
            "error": str(e),
            "resolved_at": "now()",
            "resolved_by": resolved_by,
        }).eq("id", action_id).execute())
        return {"status": "failed", "error": str(e)}

    await db._async_execute(lambda: supabase.table("pending_actions").update({
        "status": "completed",
        "result": result.to_dict(),
        "error": result.error,
        "resolved_at": "now()",
        "resolved_by": resolved_by,
    }).eq("id", action_id).execute())
    return {"status": "completed", "result": result.to_dict()}

# Mutating prefixes per the project's naming convention. Any tool whose name
# starts with one of these is treated as mutating and gated behind approval.
MUTATING_PREFIXES = ("create_", "delete_", "send_", "publish_", "update_")


def is_mutating_tool(tool_name: str) -> bool:
    """Whether a tool name is mutating by the prefix convention."""
    return tool_name.lower().startswith(MUTATING_PREFIXES)


async def queue_pending_action(
    server_id: Optional[str],
    tool_name: str,
    tool_args: dict,
    requested_by: Optional[str] = None,
) -> ToolResult:
    """Queue a mutating action for human approval. Does NOT execute it.

    Returns a ToolResult that clearly signals to the model that the action did
    NOT run and is waiting on approval — not a generic failure, so the model
    doesn't retry blindly or claim the action completed.
    """
    import db.client as db
    supabase = db.get_db()
    row = {
        "server_id": server_id,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "requested_by": requested_by,
        "status": "pending",
    }
    res = await db._async_execute(lambda: supabase.table("pending_actions").insert(row).execute())
    action_id = res.data[0]["id"] if res.data else None
    logger.info(f"Queued mutating action '{tool_name}' for approval (id={action_id})")
    return ToolResult(
        success=False,  # not an error — but the action did NOT execute
        output={
            "status": "pending_approval",
            "action_id": action_id,
            "message": (
                f"'{tool_name}' is a mutating action and requires human "
                f"approval before it runs. Queued as action {action_id}."
            ),
        },
        metadata={"pending_action_id": action_id, "requires_approval": True},
    )
