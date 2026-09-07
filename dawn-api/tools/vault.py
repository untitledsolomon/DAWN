"""
Vault tools — let the agent read and write the DAWN memory vault.

The vault is a file-based long-form memory layer (profile, daily notes,
project knowledge) that complements the structured `memories` table. These
tools expose it to the agent so it can read relevant notes before producing
output (AI priming) and write notes it learns during a conversation.

All operations are confined to the vault root — no path escapes.
"""
import logging
from tools.base import BaseTool, ToolResult
from vault import vault

logger = logging.getLogger(__name__)


class VaultReadTool(BaseTool):
    name = "vault_read"
    description = (
        "Read a note from the DAWN memory vault by path (e.g. 'Personal/Stack.md', "
        "'01 - Daily Notes/2026-09-07.md'). Use to load relevant context before "
        "answering, or to check what a note contains."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Vault-relative path to the note (e.g. 'Personal/Stack.md').",
            },
        },
        "required": ["path"],
    }

    async def run(self, path: str) -> ToolResult:
        try:
            content = vault.read_note(path)
            return ToolResult(success=True, output={"path": path, "content": content})
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"vault_read failed for {path}")
            return ToolResult(success=False, error=f"Failed to read note: {e}")


class VaultWriteTool(BaseTool):
    name = "vault_write"
    description = (
        "Write or update a note in the DAWN memory vault by path. Use to store "
        "long-form knowledge, project notes, or things worth remembering across "
        "conversations. Creates parent folders as needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Vault-relative path to the note (e.g. 'Personal/Stack.md').",
            },
            "content": {
                "type": "string",
                "description": "Full markdown content of the note.",
            },
        },
        "required": ["path", "content"],
    }

    async def run(self, path: str, content: str) -> ToolResult:
        try:
            abs_path = vault.write_note(path, content)
            return ToolResult(success=True, output={"path": path, "written_to": abs_path})
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.exception(f"vault_write failed for {path}")
            return ToolResult(success=False, error=f"Failed to write note: {e}")


class VaultListTool(BaseTool):
    name = "vault_list"
    description = (
        "List notes in the DAWN memory vault, optionally under a subfolder. "
        "Use to see what's stored and find the right note to read."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "subdir": {
                "type": "string",
                "description": "Optional subfolder to list (e.g. 'Personal'). Empty lists the whole vault.",
                "default": "",
            },
        },
        "required": [],
    }

    async def run(self, subdir: str = "") -> ToolResult:
        try:
            notes = vault.list_notes(subdir)
            return ToolResult(success=True, output={"count": len(notes), "notes": notes})
        except ValueError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            logger.exception("vault_list failed")
            return ToolResult(success=False, error=f"Failed to list notes: {e}")


class VaultDailyNoteTool(BaseTool):
    name = "vault_daily_note"
    description = (
        "Get or create today's daily note in the DAWN memory vault. Use to "
        "log what was done today, capture decisions, or review the day's work."
    )
    input_schema = {"type": "object", "properties": {}}

    async def run(self, **kwargs) -> ToolResult:
        try:
            content = vault.daily_note()
            return ToolResult(success=True, output={"content": content})
        except Exception as e:
            logger.exception("vault_daily_note failed")
            return ToolResult(success=False, error=f"Failed to get daily note: {e}")


class VaultIndexTool(BaseTool):
    name = "vault_index"
    description = (
        "Load the DAWN memory vault index — the user's profile and the vault "
        "structure. Read this at the start of a conversation to know who the "
        "user is and what's active."
    )
    input_schema = {"type": "object", "properties": {}}

    async def run(self, **kwargs) -> ToolResult:
        try:
            content = vault.load_index()
            return ToolResult(success=True, output={"content": content})
        except Exception as e:
            logger.exception("vault_index failed")
            return ToolResult(success=False, error=f"Failed to load vault index: {e}")
