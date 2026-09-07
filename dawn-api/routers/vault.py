"""
Vault API — HTTP access to the DAWN memory vault (file-based long-form memory).
"""
import logging
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from config import settings
from vault import vault

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class NoteWrite(BaseModel):
    path: str
    content: str


@router.get("/vault", tags=["vault"])
async def get_vault_index(_: None = Depends(verify_key)):
    """Return the vault index (profile + structure)."""
    try:
        return {"path": "VAULT-INDEX.md", "content": vault.load_index()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vault/notes", tags=["vault"])
async def list_vault_notes(subdir: str = "", _: None = Depends(verify_key)):
    """List vault notes, optionally under a subfolder."""
    try:
        return {"notes": vault.list_notes(subdir)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/vault/note", tags=["vault"])
async def read_vault_note(path: str, _: None = Depends(verify_key)):
    """Read a vault note by path."""
    try:
        return {"path": path, "content": vault.read_note(path)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/vault/note", tags=["vault"])
async def write_vault_note(req: NoteWrite, _: None = Depends(verify_key)):
    """Write or update a vault note by path."""
    try:
        abs_path = vault.write_note(req.path, req.content)
        return {"path": req.path, "written_to": abs_path}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
