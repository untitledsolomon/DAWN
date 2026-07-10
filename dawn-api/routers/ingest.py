"""
DAWN Ingestion Router - file upload, repo ingest, document ingest, memory ingest.

All ingestion runs in background tasks with retry logic, structured logging,
and a persistent job queue with status tracking.

Supports streaming ingestion for files up to 20GB+ - files are processed
in chunks rather than loaded entirely into memory. Scanned PDFs are OCR'd
page-by-page with configurable page limits.

v2.0 — Added auto-tagging (sentence-transformers) and multi-file/zip upload.
v2.1 — Hybrid semantic tagger: Top-K + adaptive floor + dynamic per-tag thresholds.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db
import logging
import asyncio
import io
import os
import zipfile
import time
import uuid
import tempfile
import shutil
from dataclasses import dataclass, field
from enum import Enum
from ingestion.parsers import extract_preview, parse_file, parse_epub, parse_docx, parse_pptx, parse_odp, parse_ods

logger = logging.getLogger(__name__)
router = APIRouter()

_tesseract_configured = False


def _ensure_tesseract_configured():
    global _tesseract_configured
    if _tesseract_configured:
        return
    if settings.tesseract_cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        logger.info(f"pytesseract configured: {settings.tesseract_cmd}")
    _tesseract_configured = True


SUPPORTED_EXTENSIONS = {
    ".pdf": "PDF", ".md": "Markdown", ".markdown": "Markdown",
    ".csv": "CSV", ".xlsx": "Excel", ".xls": "Excel",
    ".svg": "SVG", ".docx": "Word", ".txt": "Text",
    ".epub": "EPUB", ".html": "HTML", ".htm": "HTML",
    ".rtf": "RTF", ".json": "JSON",
    ".odt": "Word", ".ods": "Spreadsheet", ".pptx": "PowerPoint", ".odp": "Presentation",
    ".xml": "XML", ".yaml": "YAML", ".yml": "YAML",
    ".log": "Text", ".ini": "Text", ".cfg": "Text", ".conf": "Text",
}

_STREAMING_THRESHOLD_BYTES = 50 * 1024 * 1024
_MAX_UPLOAD_BYTES = 30 * 1024 * 1024 * 1024
_MAX_ZIP_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100
_MAX_SPREADSHEET_ROWS = 100_000
_MAX_OCR_PAGES = 5000
_MAX_PDF_PAGES = 10000

# Maximum body size for a single table-data child node.
# Tables larger than this get split into multiple child nodes.
_MAX_TABLE_BODY_CHARS = 50_000


class IngestionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class IngestionJob:
    id: str
    type: str
    params: dict
    status: IngestionStatus = IngestionStatus.QUEUED
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


class IngestionQueue:
    def __init__(self, max_concurrent: int = 2):
        self.queue: asyncio.Queue[IngestionJob] = asyncio.Queue()
        self.jobs: dict[str, IngestionJob] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("Ingestion queue worker started")

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
            logger.info("Ingestion queue worker stopped")

    async def enqueue(self, job: IngestionJob) -> str:
        self.jobs[job.id] = job
        await self.queue.put(job)
        return job.id

    def get_status(self, job_id: str) -> Optional[IngestionJob]:
        return self.jobs.get(job_id)

    async def _worker_loop(self):
        while True:
            try:
                job = await self.queue.get()
                async with self._semaphore:
                    job.status = IngestionStatus.RUNNING
                    job.started_at = time.time()
                    try:
                        result = await self._execute_job(job)
                        job.status = IngestionStatus.SUCCESS
                        job.result = result
                    except Exception as e:
                        job.status = IngestionStatus.FAILED
                        job.error = str(e)
                        logger.error(f"Job {job.id} ({job.type}) failed: {e}")
                    finally:
                        job.completed_at = time.time()
                        self.queue.task_done()
                        # Update or create book record on completion
                        await self._on_job_complete(job)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue worker error: {e}")
                await asyncio.sleep(1)

    async def _on_job_complete(self, job: IngestionJob):
        """After a job completes, update or create the associated book record."""
        if job.type not in ("document", "file"):
            return
        source_ref = job.params.get("source_ref", "")
        if not source_ref:
            return

        import re as _re
        is_uuid = bool(_re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', source_ref))

        try:
            supabase = db.get_db()

            if is_uuid:
                # Existing book — update its status
                book_res = supabase.table("books").select("id").eq("id", source_ref).execute()
                if not book_res.data:
                    return
                if job.status == IngestionStatus.SUCCESS:
                    supabase.table("books").update({
                        "ingestion_status": "complete",
                        "ingested": True,
                    }).eq("id", source_ref).execute()
                    logger.info(f"Book {source_ref[:8]} marked as ingested successfully")
                elif job.status == IngestionStatus.FAILED:
                    supabase.table("books").update({
                        "ingestion_status": "error",
                    }).eq("id", source_ref).execute()
                    logger.warning(f"Book {source_ref[:8]} marked as ingestion error: {job.error}")
            else:
                # File upload — create a book record if one doesn't already exist for this source_ref
                if job.status != IngestionStatus.SUCCESS:
                    return

                # Check if a book with this source_ref already exists
                existing = supabase.table("books").select("id").eq("source_ref", source_ref).execute()
                if existing.data:
                    # Update existing record
                    supabase.table("books").update({
                        "ingestion_status": "complete",
                        "ingested": True,
                    }).eq("id", existing.data[0]["id"]).execute()
                    logger.info(f"Book record updated for file: {source_ref}")
                    return

                # Create a new book record
                title = job.params.get("title", source_ref)
                tags = job.params.get("tags", [])
                category = tags[0] if tags else None

                book_data = {
                    "title": title,
                    "author": None,
                    "category": category,
                    "tags": tags,
                    "source_ref": source_ref,
                    "ingested": True,
                    "ingestion_status": "complete",
                }
                supabase.table("books").insert(book_data).execute()
                logger.info(f"Book record created for uploaded file: {title}")

        except Exception as e:
            logger.warning(f"Failed to update/create book record for {source_ref}: {e}")

    async def _execute_job(self, job: IngestionJob) -> dict:
        max_retries = 3
        base_delay = 2.0
        for attempt in range(max_retries):
            try:
                if job.type == "repo":
                    from ingestion.repo import ingest_repo
                    return await ingest_repo(**job.params)
                elif job.type == "document":
                    from ingestion.repo import ingest_document
                    return await ingest_document(**job.params)
                elif job.type == "file":
                    return await self._execute_file_job(job)
                elif job.type == "memory":
                    from ingestion.memory import ingest_memory
                    return await ingest_memory(**job.params)
                else:
                    raise ValueError(f"Unknown job type: {job.type}")
            except (asyncio.TimeoutError, ConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Retry {attempt+1}/{max_retries} for job {job.id} after {delay}s: {e}")
                await asyncio.sleep(delay)
            except Exception:
                raise

    async def _execute_file_job(self, job: IngestionJob) -> dict:
        from ingestion.repo import ingest_document_stream, ingest_sections
        file_type = job.params["file_type"]
        title = job.params["title"]
        source_ref = job.params["source_ref"]
        tags = job.params.get("tags", [])
        temp_path = job.params.get("temp_path")

        if temp_path and os.path.exists(temp_path):
            result = await self._process_streaming_file(temp_path, file_type, title, source_ref, tags)
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            return result
        else:
            file_bytes = job.params.get("file_bytes", b"")
            return await self._process_memory_file(file_bytes, file_type, title, source_ref, tags)

    async def _process_streaming_file(self, temp_path, file_type, title, source_ref, tags):
        file_size = os.path.getsize(temp_path)
        logger.info(f"Processing streamed file: {source_ref} ({file_size / 1e9:.2f} GB)")
        with open(temp_path, "rb") as f:
            file_bytes = f.read()
        return await self._process_memory_file(file_bytes, file_type, title, source_ref, tags)

    async def _process_memory_file(self, file_bytes, file_type, title, source_ref, tags):
        from ingestion.repo import ingest_document_stream, ingest_sections
        if file_type == "PDF":
            peek_gen = _peek_pdf_pages(file_bytes, sample_pages=5)
            if peek_gen is None:
                sample_text = ""
            else:
                sample_text = "".join(peek_gen)

            if len(sample_text.strip()) < 20:
                logger.warning(f"PDF '{source_ref}' looks scanned - using OCR.")
                ocr_gen = _iter_ocr_pdf_pages(file_bytes)
                if ocr_gen is None:
                    logger.warning(f"OCR unavailable for '{source_ref}' - falling back to text layer.")
                    pdf_gen = iter_pdf_pages(file_bytes)
                    gen = pdf_gen if pdf_gen is not None else iter([])
                else:
                    gen = ocr_gen
            else:
                pdf_gen = iter_pdf_pages(file_bytes)
                gen = pdf_gen if pdf_gen is not None else iter([])

            result = await ingest_document_stream(title, gen, source_ref, tags)
        elif file_type == "Word":
            sections = parse_docx(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        elif file_type == "PowerPoint":
            sections = parse_pptx(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        elif file_type == "Presentation":
            sections = parse_odp(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        elif file_type == "Spreadsheet":
            sections = parse_ods(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        elif file_type == "EPUB":
            sections = parse_epub(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        else:
            extraction = _extract_content(file_bytes, file_type, source_ref, title)
            if extraction.get("sections"):
                result = await ingest_sections(title, extraction["sections"], source_ref, tags)
            else:
                from ingestion.repo import ingest_document
                result = await ingest_document(title, extraction["text"], source_ref, tags)
        await db.log_ingestion({
            "source": "document", "source_ref": source_ref,
            "nodes_created": result["nodes_created"],
            "edges_created": result.get("edges_created", 0),
            "status": "success",
        })
        return result


ingestion_queue = IngestionQueue(max_concurrent=2)


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class RepoIngestRequest(BaseModel):
    repo_path: str
    repo_name: str
    tags: list[str] = []


class DocumentIngestRequest(BaseModel):
    title: str
    content: str
    source_ref: str = ""
    tags: list[str] = []


class MemoryIngestRequest(BaseModel):
    conversation: str
    session_source: str = "manual"


@router.post("/repo")
async def ingest_repo_endpoint(req: RepoIngestRequest, _: None = Depends(verify_key)):
    job = IngestionJob(id=str(uuid.uuid4()), type="repo",
        params={"repo_path": req.repo_path, "repo_name": req.repo_name, "tags": req.tags})
    await ingestion_queue.enqueue(job)
    return {"status": "queued", "job_id": job.id, "repo": req.repo_name}


@router.post("/document")
async def ingest_document_endpoint(req: DocumentIngestRequest, _: None = Depends(verify_key)):
    job = IngestionJob(id=str(uuid.uuid4()), type="document",
        params={"title": req.title, "content": req.content, "source_ref": req.source_ref, "tags": req.tags})
    await ingestion_queue.enqueue(job)
    return {"status": "queued", "job_id": job.id, "title": req.title}


@router.post("/memory")
async def ingest_memory_endpoint(req: MemoryIngestRequest, _: None = Depends(verify_key)):
    job = IngestionJob(id=str(uuid.uuid4()), type="memory",
        params={"conversation": req.conversation, "session_source": req.session_source})
    await ingestion_queue.enqueue(job)
    return {"status": "queued", "job_id": job.id}


@router.get("/status/{job_id}")
async def get_job_status(job_id: str, _: None = Depends(verify_key)):
    job = ingestion_queue.get_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id, "type": job.type, "status": job.status.value,
        "error": job.error, "result": job.result,
        "created_at": job.created_at, "started_at": job.started_at, "completed_at": job.completed_at,
    }


# ─── Auto-Tagging (v2.1 — Hybrid Tagger) ──────────────────────────────────────
# Uses the HybridTagger from ingestion/tagger.py which implements:
#   1. Top-K (always returns top 2 tags)
#   2. Adaptive floor (0.1 minimum — garbage detection)
#   3. Dynamic per-tag thresholds (learned from historical matches)
# No extra dependencies, no API calls, runs on CPU.

_tagger_instance = None


async def _get_tagger():
    """Lazy-load and return the singleton HybridTagger instance."""
    global _tagger_instance
    if _tagger_instance is None:
        from ingestion.tagger import HybridTagger
        _tagger_instance = HybridTagger()
        await _tagger_instance.refresh()
    return _tagger_instance


async def _auto_tag_content(content: str, title: str = "", top_n: int = 2, threshold: float = 0.1) -> list[str]:
    """Auto-tag document content using the hybrid semantic tagger.

    Uses Top-K (top_n) + adaptive floor (threshold) + dynamic per-tag thresholds.
    Falls back to ["uncategorized"] if nothing clears the bar.
    """
    tagger = await _get_tagger()
    return await tagger.tag(
        text=content,
        title=title,
        top_k=top_n,
        min_similarity=threshold,
        use_dynamic_thresholds=True,
    )


# ─── Single File Upload ───────────────────────────────────────────────────────

@router.post("/file")
async def ingest_file(
    file: UploadFile = File(...),
    title: str = Form(""),
    tags: str = Form(""),
    x_api_key: Optional[str] = Header(None),
):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    filename = file.filename or ""
    ext = os.path.splitext(filename.lower())[1]
    file_type = SUPPORTED_EXTENSIONS.get(ext)
    if not file_type:
        raise HTTPException(status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(set(SUPPORTED_EXTENSIONS.values())))}")

    doc_title = title.strip() or os.path.splitext(filename)[0]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Read first bytes for validation, then decide streaming vs memory
    header_bytes = await file.read(8192)
    if not header_bytes:
        raise HTTPException(status_code=422, detail="Empty file")

    # Quick sanity check
    if not _quick_sanity_check(header_bytes, file_type):
        raise HTTPException(status_code=422, detail=f"File does not look like a valid {file_type} file.")

    # Zip-bomb check for zip-based formats
    if file_type in ("Word", "EPUB", "Excel"):
        full_check_bytes = header_bytes + await file.read()
        zip_error = _check_zip_safety(full_check_bytes)
        if zip_error:
            raise HTTPException(status_code=422, detail=zip_error)
        file_bytes = full_check_bytes
        total_size = len(file_bytes)
    else:
        remaining = await file.read()
        file_bytes = header_bytes + remaining
        total_size = len(file_bytes)

    if total_size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
            detail=f"File is {total_size / 1e9:.2f}GB, exceeds {_MAX_UPLOAD_BYTES // (1024*1024*1024)}GB limit.")

    # ── Auto-tag if no tags provided ──
    if not tag_list:
        # Extract a preview of the content for classification
        preview = _extract_preview(file_bytes, file_type, filename)
        tag_list = await _auto_tag_content(preview, doc_title)
        logger.info(f"Auto-tagged '{filename}' as: {tag_list}")

    # For files > streaming threshold, write to temp file
    temp_path = None
    if total_size > _STREAMING_THRESHOLD_BYTES:
        fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1])
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)
        logger.info(f"Large file ({total_size / 1e6:.1f}MB) streamed to temp: {temp_path}")
        job = IngestionJob(id=str(uuid.uuid4()), type="file",
            params={"title": doc_title, "source_ref": filename, "file_type": file_type,
                    "temp_path": temp_path, "tags": tag_list})
    else:
        job = IngestionJob(id=str(uuid.uuid4()), type="file",
            params={"title": doc_title, "source_ref": filename, "file_type": file_type,
                    "file_bytes": file_bytes, "tags": tag_list})

    await ingestion_queue.enqueue(job)
    return {
        "status": "queued", "job_id": job.id, "title": doc_title,
        "file_type": file_type, "filename": filename,
        "tags": tag_list,
        "size_mb": total_size / 1e6,
        "note": f"File ({total_size / 1e6:.1f}MB) queued for ingestion." if total_size > _STREAMING_THRESHOLD_BYTES else None,
    }


# ─── Multi-File / Zip Upload ──────────────────────────────────────────────────

@router.post("/files")
async def ingest_files(
    files: list[UploadFile] = File(...),
    tags: str = Form(""),
    x_api_key: Optional[str] = Header(None),
):
    """Upload multiple files and/or zip archives at once.

    Accepts:
    - Multiple individual files (any supported type)
    - .zip archives (extracted automatically, each supported file ingested)
    - A mix of both

    Returns a summary with job IDs for each file.
    """
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    global_tags = [t.strip() for t in tags.split(",") if t.strip()]
    jobs = []
    errors = []

    for file in files:
        filename = file.filename or ""
        if not filename:
            continue

        ext = os.path.splitext(filename.lower())[1]

        # ── Zip archive handling ──
        if ext == ".zip":
            try:
                raw_bytes = await file.read()
                if not raw_bytes:
                    errors.append({"file": filename, "error": "Empty zip file"})
                    continue
                zip_jobs, zip_errors = await _process_zip_upload(
                    raw_bytes, filename, global_tags
                )
                jobs.extend(zip_jobs)
                errors.extend(zip_errors)
            except Exception as e:
                errors.append({"file": filename, "error": f"Zip processing failed: {str(e)}"})
            continue

        # ── Individual file handling ──
        file_type = SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            errors.append({"file": filename, "error": f"Unsupported file type '{ext}'"})
            continue

        doc_title = os.path.splitext(filename)[0]
        tag_list = list(global_tags)  # copy

        # Read the file
        file_bytes = await file.read()
        if not file_bytes:
            errors.append({"file": filename, "error": "Empty file"})
            continue

        total_size = len(file_bytes)
        if total_size > _MAX_UPLOAD_BYTES:
            errors.append({"file": filename, "error": f"File exceeds size limit"})
            continue

        # Quick sanity check
        if not _quick_sanity_check(file_bytes[:8192], file_type):
            errors.append({"file": filename, "error": f"File does not look like a valid {file_type}"})
            continue

        # Auto-tag if no global tags provided
        if not tag_list:
            preview = _extract_preview(file_bytes, file_type, filename)
            tag_list = await _auto_tag_content(preview, doc_title)
            logger.info(f"Auto-tagged '{filename}' as: {tag_list}")

        # Queue the job
        job = IngestionJob(id=str(uuid.uuid4()), type="file",
            params={"title": doc_title, "source_ref": filename, "file_type": file_type,
                    "file_bytes": file_bytes, "tags": tag_list})
        await ingestion_queue.enqueue(job)
        jobs.append({
            "job_id": job.id, "filename": filename, "file_type": file_type,
            "tags": tag_list, "size_mb": total_size / 1e6,
        })

    return {
        "status": "complete",
        "total_files": len(jobs) + len(errors),
        "queued": len(jobs),
        "errors": len(errors),
        "jobs": jobs,
        "error_details": errors if errors else None,
    }


async def _process_zip_upload(
    zip_bytes: bytes, zip_filename: str, global_tags: list[str]
) -> tuple[list[dict], list[dict]]:
    """Extract a zip archive and queue ingestion jobs for each supported file.

    Returns (jobs_list, errors_list).
    """
    jobs = []
    errors = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        errors.append({"file": zip_filename, "error": "Invalid zip file"})
        return jobs, errors

    # Safety checks
    total_uncompressed = 0
    for info in zf.infolist():
        total_uncompressed += info.file_size
        if info.file_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
            errors.append({"file": info.filename, "error": "File too large in zip"})
            continue
        if info.compress_size > 0:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > _MAX_ZIP_COMPRESSION_RATIO and info.file_size > 10_000_000:
                errors.append({"file": info.filename, "error": "Suspicious compression ratio"})
                continue

    if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
        errors.append({"file": zip_filename, "error": "Zip expands to over 500MB"})
        zf.close()
        return jobs, errors

    # Extract and process each file
    for info in zf.infolist():
        fname = info.filename

        # Skip directories, macOS metadata, hidden files
        if fname.endswith("/"):
            continue
        if fname.startswith("__MACOSX/") or fname.startswith("."):
            continue
        if os.path.basename(fname).startswith("."):
            continue

        ext = os.path.splitext(fname.lower())[1]
        file_type = SUPPORTED_EXTENSIONS.get(ext)
        if not file_type:
            continue

        try:
            file_bytes = zf.read(info.filename)
        except Exception as e:
            errors.append({"file": f"{zip_filename}/{fname}", "error": f"Read failed: {str(e)}"})
            continue

        if not file_bytes:
            continue

        doc_title = os.path.splitext(os.path.basename(fname))[0]
        tag_list = list(global_tags)

        # Auto-tag if no global tags
        if not tag_list:
            preview = _extract_preview(file_bytes, file_type, fname)
            tag_list = await _auto_tag_content(preview, doc_title)

        source_ref = f"{zip_filename}/{fname}"
        job = IngestionJob(id=str(uuid.uuid4()), type="file",
            params={"title": doc_title, "source_ref": source_ref, "file_type": file_type,
                    "file_bytes": file_bytes, "tags": tag_list})
        await ingestion_queue.enqueue(job)
        jobs.append({
            "job_id": job.id, "filename": source_ref, "file_type": file_type,
            "tags": tag_list, "size_mb": len(file_bytes) / 1e6,
        })

    zf.close()
    return jobs, errors


# ─── Content Preview Extraction (for auto-tagging) ────────────────────────────

# ── Content Preview Extraction (for auto-tagging) ─────────────────────────────
# Delegated to ingestion.parsers.extract_preview

def _extract_preview(file_bytes: bytes, file_type: str, filename: str, max_chars: int = 1000) -> str:
    """Extract a text preview from a file for auto-tagging classification.
    
    Delegates to the unified parser module which handles all formats.
    PDF is handled specially with OCR fallback.
    """
    if file_type == "PDF":
        gen = iter_pdf_pages(file_bytes)
        if gen:
            text = " ".join(gen)
            return text[:max_chars] if text else ""
        ocr = _iter_ocr_pdf_pages(file_bytes, max_pages=3)
        if ocr:
            text = " ".join(ocr)
            return text[:max_chars] if text else ""
        return ""
    return extract_preview(file_bytes, filename, max_chars)


# ─── Stats & Log Endpoints ────────────────────────────────────────────────────

@router.get("/stats")
async def ingestion_stats(_: None = Depends(verify_key)):
    try:
        failed_recent = await db.get_failed_ingestions_since(time.time() - 86400)
        total_nodes = await db.count_nodes()
        db_ok = await db.ping()
    except Exception:
        failed_recent = []; total_nodes = 0; db_ok = False
    active_jobs = sum(1 for j in ingestion_queue.jobs.values()
                      if j.status in (IngestionStatus.QUEUED, IngestionStatus.RUNNING))
    return {
        "queue_depth": ingestion_queue.queue.qsize(), "active_jobs": active_jobs,
        "failed_last_24h": len(failed_recent), "total_nodes": total_nodes, "db_connected": db_ok,
    }


@router.get("/log")
async def get_log(_: None = Depends(verify_key)):
    return await db.get_ingestion_log()



# ──── Admin: Back-Tag Existing Nodes ──────────────────────────────────────────
# Re-runs auto-tagging on all nodes tagged "uncategorized" or with no tags.
# Uses the HybridTagger with Top-K + adaptive floor + dynamic per-tag thresholds.
# Also updates per-tag thresholds based on match scores for continuous learning.
# Trigger via: POST /admin/backtag (requires API key)

NEW_TAGS_FOR_BACKTAG = [
    {"name": "self-help", "description": "Self-help, personal development, psychology, philosophy, life strategy, success principles, motivation"},
    {"name": "philosophy", "description": "Philosophy, ethics, political theory, historical analysis, critical thinking, logic, morality"},
    {"name": "psychology", "description": "Psychology, human behavior, cognitive science, persuasion, influence, mental models"},
    {"name": "history", "description": "History, historical events, biographies, historical analysis, ancient civilizations, world history"},
    {"name": "strategy", "description": "Strategy, tactics, game theory, military strategy, business strategy, competitive analysis, power dynamics"},
    {"name": "leadership", "description": "Leadership, management, executive skills, team building, organizational behavior, decision making"},
    {"name": "communication", "description": "Communication, negotiation, persuasion, public speaking, rhetoric, writing, storytelling"},
    {"name": "economics", "description": "Economics, macroeconomics, microeconomics, economic theory, market analysis, trade"},
    {"name": "politics", "description": "Politics, governance, political theory, international relations, policy, power"},
    {"name": "biography", "description": "Biography, memoir, autobiography, personal stories, life narratives, historical figures"},
    {"name": "uncategorized", "description": "Default fallback tag for content that doesn't match any other category"},
    {"name": "robert greene", "description": "Robert Greene, author of The 48 Laws of Power, The Art of Seduction, Mastery, power dynamics, strategy, historical examples, manipulation, human nature"},
    {"name": "books", "description": "Books, reading, literature, authors, publishing, book summaries, literary analysis"},
]


@router.post("/admin/backtag")
async def admin_backtag(x_api_key: Optional[str] = Header(None)):
    """Re-run auto-tagging on all uncategorized/untagged nodes.

    Uses the HybridTagger with:
    - Top-K (top 2 tags per node)
    - Adaptive floor (0.1 minimum similarity)
    - Dynamic per-tag thresholds (learned from match scores)

    Also creates any missing tags from NEW_TAGS_FOR_BACKTAG in the database.
    Returns a summary of what was tagged and what stayed uncategorized.
    """
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    results = {"tags_created": 0, "nodes_processed": 0, "tagged": 0, "still_uncategorized": 0, "errors": 0}

    # Step 1: Add any missing tags
    existing_tags = await db.get_all_tags()
    existing_names = {t["name"] for t in existing_tags}
    for tag_def in NEW_TAGS_FOR_BACKTAG:
        if tag_def["name"] not in existing_names:
            await db.create_tag(tag_def["name"], tag_def["description"])
            results["tags_created"] += 1
            logger.info(f"Backtag: created tag '{tag_def['name']}'")

    # Refresh tag list
    all_tags = await db.get_all_tags()
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}

    # Step 2: Find uncategorized and untagged nodes
    db_client = db.get_db()

    # Find the uncategorized tag ID
    uncat_tag = next((t for t in all_tags if t["name"] == "uncategorized"), None)
    uncat_tag_id = uncat_tag["id"] if uncat_tag else None

    # Nodes with "uncategorized" tag
    uncategorized_ids = set()
    if uncat_tag_id:
        res = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db_client.table("node_tags")
            .select("node_id")
            .eq("tag_id", uncat_tag_id)
            .execute()
        )
        uncategorized_ids = {row["node_id"] for row in (res.data or [])}

    # All nodes with ANY tag
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("node_tags").select("node_id").execute()
    )
    any_tag_ids = {row["node_id"] for row in (res.data or [])}

    # All active/stale nodes
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("nodes")
        .select("id, title, body, type, source, source_ref")
        .in_("status", ["active", "stale"])
        .execute()
    )
    all_nodes = res.data or []

    nodes_to_tag = []
    for node in all_nodes:
        nid = node["id"]
        if nid in uncategorized_ids or nid not in any_tag_ids:
            nodes_to_tag.append(node)

    results["nodes_processed"] = len(nodes_to_tag)

    if not nodes_to_tag:
        return {**results, "message": "No uncategorized or untagged nodes found."}

    tagger = await _get_tagger()
    await tagger.refresh()

    # Step 4: Back-tag each node using the hybrid strategy
    for i, node in enumerate(nodes_to_tag):
        try:
            title = node.get("title", "") or ""
            body = node.get("body", "") or ""
            text = f"{title} {body}" if title else body
            text = text.strip()
            if not text:
                continue

            matched = await tagger.tag(
                text=text,
                title="",
                top_k=2,
                min_similarity=0.1,
                use_dynamic_thresholds=True,
            )

            if matched and matched != ["uncategorized"]:
                tag_ids = [tag_name_to_id[t] for t in matched if t in tag_name_to_id]
                if tag_ids:
                    await db.attach_tags_batch([node["id"]], tag_ids)
                    results["tagged"] += 1

                    if tagger.model is not None and tagger.tag_embeddings:
                        import numpy as np
                        doc_vec = tagger.model.encode(text[:2000], show_progress_bar=False)
                        doc_norm = doc_vec / (np.linalg.norm(doc_vec) + 1e-10)
                        for tag_name in matched:
                            tag_vec = tagger.tag_embeddings.get(tag_name)
                            if tag_vec is not None:
                                tag_norm = tag_vec / (np.linalg.norm(tag_vec) + 1e-10)
                                score = float(np.dot(doc_norm, tag_norm))
                                await tagger.update_threshold(tag_name, score)
            else:
                results["still_uncategorized"] += 1

        except Exception as e:
            results["errors"] += 1
            logger.error(f"Backtag error on node {node.get('id', '?')[:8]}: {e}")

    thresholds = await tagger.get_thresholds()
    logger.info(f"Backtag complete. Per-tag thresholds: {thresholds}")

    return {
        **results,
        "thresholds": {k: round(v, 3) for k, v in thresholds.items()},
        "message": (
            f"Processed {results['nodes_processed']} nodes. "
            f"Tagged {results['tagged']}, {results['still_uncategorized']} still uncategorized. "
            f"Per-tag thresholds updated."
        ),
    }


# ── File Type Detection ───────────────────────────────────────────────────────
# Delegated to ingestion.parsers.detect_file_type

def detect_file_type(filename: str) -> Optional[str]:
    """Detect file type from filename extension. Delegates to parsers module."""
    from ingestion.parsers import detect_file_type as _detect
    return _detect(filename)


def _check_zip_safety(file_bytes: bytes) -> Optional[str]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        return "File is not a valid zip-based document."
    total_uncompressed = 0
    for info in zf.infolist():
        total_uncompressed += info.file_size
        if info.file_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
            return f"Archive member expands to over {_MAX_ZIP_UNCOMPRESSED_BYTES // (1024*1024)}MB."
        if info.compress_size > 0:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > _MAX_ZIP_COMPRESSION_RATIO and info.file_size > 10_000_000:
                return "Suspicious compression ratio (possible zip bomb)."
    if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
        return f"Archive expands to over {_MAX_ZIP_UNCOMPRESSED_BYTES // (1024*1024)}MB total."
    return None


def _quick_sanity_check(file_bytes: bytes, file_type: str) -> bool:
    try:
        if file_type == "PDF":
            return file_bytes[:5] == b"%PDF-"
        if file_type in ("Word", "EPUB", "Excel", "PowerPoint", "Presentation", "MOBI", "FB2", "ODT"):
            return file_bytes[:2] == b"PK"
        if file_type == "XML":
            return file_bytes[:5].lstrip()[:1] == b"<" or file_bytes[:5] == b"<?xml"
        if file_type == "SVG":
            return file_bytes[:5].lstrip()[:1] == b"<"
        if file_type == "DjVu":
            return file_bytes[:4] == b"AT&T"
        if file_type == "LaTeX":
            return file_bytes[:1] == b"\\"
        return True
    except Exception:
        return False


def _extract_content(file_bytes: bytes, file_type: str, filename: str, doc_title: str = "") -> dict:
    """Extract content from a file. Delegates to the unified parser module."""
    result = parse_file(file_bytes, filename, doc_title)
    return {
        "text": result.get("text", ""),
        "sections": result.get("sections", []),
    }


# ── PDF Parsing ───────────────────────────────────────────────────────────────
# PDF is handled natively in this router because of OCR support

def _parse_pdf(file_bytes: bytes) -> str:
    pdf_gen = iter_pdf_pages(file_bytes)
    if pdf_gen is None:
        logger.warning("PDF text layer unavailable - trying OCR.")
        ocr_result = _ocr_pdf(file_bytes)
        return ocr_result
    result = "\n\n".join(pdf_gen)
    if len(result.strip()) < 20:
        logger.warning(f"PDF text layer near-empty ({len(result.strip())} chars) - trying OCR.")
        ocr_result = _ocr_pdf(file_bytes)
        if len(ocr_result.strip()) > len(result.strip()):
            return ocr_result
    return result


def _ocr_pdf(file_bytes: bytes, max_pages: int = 300) -> str:
    try:
        import fitz, pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR fallback unavailable.")
        return ""
    _ensure_tesseract_configured()
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        logger.warning("Failed to open PDF for OCR - file may be corrupt.")
        return ""
    pages_text = []
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)
    try:
        for i in range(pages_to_process):
            page = doc[i]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            if text and text.strip():
                pages_text.append(text.strip())
    except Exception as e:
        logger.error(f"OCR failed partway: {e}")
    finally:
        doc.close()
    if total_pages > max_pages:
        pages_text.append(f"[OCR truncated: {total_pages} pages, only first {max_pages} OCR'd.]")
    return "\n\n".join(pages_text)


def iter_pdf_pages(file_bytes: bytes):
    try:
        import fitz
    except ImportError:
        logger.warning("fitz (pymupdf) not available - PDF text extraction disabled.")
        return None
    import fitz
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        logger.warning("Failed to open PDF stream - file may be corrupt or empty.")
        return
    try:
        for i, page in enumerate(doc):
            if i >= _MAX_PDF_PAGES:
                yield f"[Truncated: PDF has more than {_MAX_PDF_PAGES} pages.]"
                break
            text = page.get_text("text")
            if text and text.strip():
                yield text.strip()
    finally:
        doc.close()


def _peek_pdf_pages(file_bytes: bytes, sample_pages: int = 5):
    """Peek at first few pages of a PDF. Returns None if fitz is unavailable or file is corrupt."""
    try:
        import fitz
    except ImportError:
        logger.warning("fitz (pymupdf) not available - PDF peek disabled.")
        return None
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        logger.warning("Failed to open PDF for peek - file may be corrupt.")
        return None
    try:
        for i in range(min(sample_pages, len(doc))):
            text = doc[i].get_text("text")
            if text:
                yield text
    finally:
        doc.close()


def _iter_ocr_pdf_pages(file_bytes: bytes, max_pages: int = 5000):
    """OCR a PDF page-by-page. Returns None if OCR deps are unavailable or file is corrupt."""
    try:
        import fitz, pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR fallback unavailable.")
        return None
    _ensure_tesseract_configured()
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception:
        logger.warning("Failed to open PDF for OCR streaming - file may be corrupt.")
        return None
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)
    try:
        for i in range(pages_to_process):
            try:
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = pytesseract.image_to_string(img)
                if text and text.strip():
                    yield text.strip()
            except Exception as e:
                logger.warning(f"OCR failed on page {i}: {e}")
                continue
    finally:
        doc.close()
    if total_pages > max_pages:
        yield f"[OCR truncated: {total_pages} pages, only first {max_pages} OCR'd.]"


# ── URL Ingestion ─────────────────────────────────────────────────────────────
# Fetches content from a URL and ingests it as a document.

class UrlIngestRequest(BaseModel):
    url: str
    title: str = ""
    tags: list[str] = []


@router.post("/url")
async def ingest_url_endpoint(req: UrlIngestRequest, _: None = Depends(verify_key)):
    """Ingest content from a URL. Fetches the URL, detects file type, and queues ingestion."""
    import httpx

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="URL is required")

    doc_title = req.title.strip() or url.split("/")[-1].split("?")[0] or "URL Document"
    tag_list = list(req.tags)

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            file_bytes = resp.content
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"URL returned {e.response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    if not file_bytes:
        raise HTTPException(status_code=422, detail="Empty response from URL")

    # Detect file type from URL or content-type
    filename = url.split("/")[-1].split("?")[0]
    ext = os.path.splitext(filename.lower())[1]
    file_type = SUPPORTED_EXTENSIONS.get(ext)

    if not file_type:
        # Try to detect from content-type
        ct_map = {
            "application/pdf": "PDF",
            "text/markdown": "Markdown",
            "text/plain": "Text",
            "text/html": "HTML",
            "application/epub+zip": "EPUB",
            "application/json": "JSON",
            "text/csv": "CSV",
            "application/xml": "XML",
            "text/xml": "XML",
            "application/rtf": "RTF",
        }
        for ct_key, ft_val in ct_map.items():
            if ct_key in content_type:
                file_type = ft_val
                break

    if not file_type:
        # Fall back to document ingestion with raw text
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("utf-8", errors="replace")

        # Auto-tag if no tags
        if not tag_list:
            tag_list = await _auto_tag_content(text[:1000], doc_title)

        job = IngestionJob(id=str(uuid.uuid4()), type="document",
            params={"title": doc_title, "content": text, "source_ref": url, "tags": tag_list})
        await ingestion_queue.enqueue(job)
        return {
            "status": "queued", "job_id": job.id, "title": doc_title,
            "source_url": url, "tags": tag_list, "file_type": "Text",
        }

    # Auto-tag if no tags
    if not tag_list:
        preview = _extract_preview(file_bytes, file_type, filename)
        tag_list = await _auto_tag_content(preview, doc_title)

    # Queue as file job
    job = IngestionJob(id=str(uuid.uuid4()), type="file",
        params={"title": doc_title, "source_ref": url, "file_type": file_type,
                "file_bytes": file_bytes, "tags": tag_list})
    await ingestion_queue.enqueue(job)

    return {
        "status": "queued", "job_id": job.id, "title": doc_title,
        "source_url": url, "tags": tag_list, "file_type": file_type,
        "size_mb": len(file_bytes) / 1e6,
    }
