"""
Files API — upload, list, and download arbitrary files.

Files are stored on local disk under `files_root` and registered in the
`artifacts` table (type='file') with the on-disk path in the `url` column.
This gives a place for user-uploaded files and DAWN-generated files that can
be downloaded, distinct from ingested knowledge (which becomes nodes).
"""
import logging
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _files_root() -> Path:
    root = Path(getattr(settings, "files_root", None) or "./files").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.get("/files", tags=["files"])
async def list_files(
    type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: None = Depends(verify_key),
):
    """List uploaded/generated files (artifacts of type 'file')."""
    try:
        supabase = db.get_db()
        q = supabase.table("artifacts").select(
            "id, title, description, type, url, tags, created_at"
        ).eq("type", "file")
        if type:
            q = q.eq("type", type)
        res = await db._async_execute(lambda: q.order("created_at", desc=True).range(offset, offset + limit - 1).execute())
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/files/upload", tags=["files"])
async def upload_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: str = Form(""),
    _: None = Depends(verify_key),
):
    """Upload a file, store it on disk, and register it as a file artifact."""
    try:
        safe_name = Path(file.filename or "file").name
        stored_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
        dest = _files_root() / stored_name

        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)

        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        # Register as a file artifact. Files aren't session-bound, so we omit
        # session_id (the column is nullable) rather than inserting a fake UUID
        # that would violate the FK to chat_sessions.
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("artifacts").insert({
            "type": "file",
            "title": title or safe_name,
            "url": str(dest),
            "tags": tag_list,
        }).execute())

        if not res.data:
            return HTTPException(status_code=500, detail="Failed to register file")

        artifact = res.data[0]
        return {
            "id": artifact["id"],
            "title": artifact["title"],
            "filename": safe_name,
            "stored_path": str(dest),
            "size": dest.stat().st_size,
            "tags": tag_list,
        }
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/{artifact_id}/download", tags=["files"])
async def download_file(artifact_id: str, _: None = Depends(verify_key)):
    """Download a file artifact by id."""
    try:
        supabase = db.get_db()
        res = await db._async_execute(lambda: supabase.table("artifacts").select(
            "id, title, url"
        ).eq("id", artifact_id).eq("type", "file").execute())
        if not res.data:
            raise HTTPException(status_code=404, detail="File not found")
        artifact = res.data[0]
        path = Path(artifact["url"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail="File missing on disk")
        return FileResponse(
            path,
            filename=artifact["title"] or path.name,
            media_type="application/octet-stream",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
