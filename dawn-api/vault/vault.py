"""
DAWN Memory Vault — a file-based long-form memory layer.

The vault is a folder of plain-text markdown notes (the "memory vault"
concept from ai-memory-vault / fullstack-agent). It complements the
structured `memories` table: the DB holds searchable facts (preferences,
decisions) with embeddings and confidence; the vault holds long-form,
absorbable context — the user's profile, project knowledge, daily logs,
and reference material.

The agent reads the vault index at the start of a conversation and uses
vault tools to read/write notes. All file access is confined to the vault
root (no path escapes), matching the sandbox pattern used elsewhere.

Layout (mirrors the vault convention):
    VAULT-INDEX.md      — profile + structure, read at conversation start
    00 - Inbox/         — capture
    01 - Daily Notes/   — dated logs, one file per day
    <Project>/          — project knowledge
    Personal/           — life outside work
    ......
"""
from datetime import datetime, timezone
from pathlib import Path
import logging

from config import settings

logger = logging.getLogger(__name__)

INDEX_FILENAME = "VAULT-INDEX.md"
DAILY_NOTES_DIR = "01 - Daily Notes"


def _vault_root() -> Path:
    root = Path(getattr(settings, "vault_root", None) or "./vault").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(rel_path: str) -> Path:
    """Resolve a vault-relative path, refusing escapes outside the vault root."""
    root = _vault_root()
    candidate = (root / rel_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError(f"Path '{rel_path}' escapes the vault root")
    return candidate


def vault_root() -> str:
    return str(_vault_root())


# ── Index ──────────────────────────────────────────────────────────────────

def ensure_index() -> str:
    """Create the vault index if it doesn't exist; return its contents."""
    index_path = _vault_root() / INDEX_FILENAME
    if not index_path.is_file():
        index_path.write_text(_DEFAULT_INDEX, encoding="utf-8")
    return index_path.read_text(encoding="utf-8")


def load_index() -> str:
    """Return the vault index contents (creating it if missing)."""
    return ensure_index()


# ── Notes ─────────────────────────────────────────────────────────────────

def read_note(rel_path: str) -> str:
    """Read a note by vault-relative path."""
    path = _safe_path(rel_path)
    if not path.is_file():
        raise FileNotFoundError(f"Note '{rel_path}' not found")
    return path.read_text(encoding="utf-8")


def write_note(rel_path: str, content: str) -> str:
    """Write a note (creating parent dirs). Returns the absolute path."""
    path = _safe_path(rel_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def list_notes(subdir: str = "") -> list[str]:
    """List markdown notes under a vault subdir (recursively), as
    vault-relative paths."""
    root = _vault_root()
    base = _safe_path(subdir) if subdir else root
    if not base.is_dir():
        return []
    notes = []
    for p in sorted(base.rglob("*.md")):
        notes.append(str(p.relative_to(root)))
    return notes


def daily_note() -> str:
    """Get or create today's daily note; return its contents."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rel = f"{DAILY_NOTES_DIR}/{today}.md"
    path = _safe_path(rel)
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {today}\n\n", encoding="utf-8")
    return path.read_text(encoding="utf-8")


_DEFAULT_INDEX = """# VAULT INDEX

Read this at the start of every conversation. It holds the profile of the
person DAWN works for and the map of this vault.

## Who I Am

[FILL IN: name and context — what you do, where you're based.]

## Vault Structure

```
00 - Inbox          ← Capture everything, sort later
01 - Daily Notes    ← Dated logs of what got done, one file per day
Personal           ← Life outside work
Archive            ← Completed projects and old notes
Resources          ← Cross-project reference material
```

## What's Active Right Now

[FILL IN: current open work and priorities.]
"""
