"""
DAWN Ingestion Router - file upload, repo ingest, document ingest, memory ingest.

All ingestion runs in background tasks with retry logic, structured logging,
and a persistent job queue with status tracking.

Supports streaming ingestion for files up to 20GB+ - files are processed
in chunks rather than loaded entirely into memory. Scanned PDFs are OCR'd
page-by-page with configurable page limits.
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
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue worker error: {e}")
                await asyncio.sleep(1)

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
            # Peek first 5 pages to detect scanned vs text PDF
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
            sections = _parse_docx(file_bytes)
            result = await ingest_sections(title, sections, source_ref, tags)
        elif file_type == "EPUB":
            sections = _parse_epub(file_bytes)
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
    file_type = detect_file_type(filename)
    if not file_type:
        ext = os.path.splitext(filename.lower())[1]
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
        # Reconstruct full bytes
        file_bytes = full_check_bytes
        total_size = len(file_bytes)
    else:
        # Read remaining
        remaining = await file.read()
        file_bytes = header_bytes + remaining
        total_size = len(file_bytes)

    if total_size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
            detail=f"File is {total_size / 1e9:.2f}GB, exceeds {_MAX_UPLOAD_BYTES // (1024*1024*1024)}GB limit.")

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
        "size_mb": total_size / 1e6,
        "note": f"File ({total_size / 1e6:.1f}MB) queued for ingestion." if total_size > _STREAMING_THRESHOLD_BYTES else None,
    }


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


def detect_file_type(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename.lower())[1]
    return SUPPORTED_EXTENSIONS.get(ext)


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
        if file_type in ("Word", "EPUB", "Excel"):
            return file_bytes[:2] == b"PK"
        return True
    except Exception:
        return False


def _extract_content(file_bytes: bytes, file_type: str, filename: str, doc_title: str = "") -> dict:
    """Extract content from a file. doc_title is used for table summaries."""
    try:
        if file_type == "PDF":
            return {"text": _parse_pdf(file_bytes), "sections": []}
        elif file_type == "Markdown":
            return {"text": "", "sections": _parse_md(file_bytes.decode("utf-8", errors="ignore"))}
        elif file_type == "CSV":
            return {"text": "", "sections": _parse_csv(file_bytes, doc_title or os.path.splitext(filename)[0])}
        elif file_type == "Excel":
            return {"text": "", "sections": _parse_xlsx(file_bytes, doc_title or os.path.splitext(filename)[0])}
        elif file_type == "SVG":
            return {"text": _parse_svg(file_bytes), "sections": []}
        elif file_type == "Word":
            return {"text": "", "sections": _parse_docx(file_bytes)}
        elif file_type == "Text":
            return {"text": _parse_txt(file_bytes), "sections": []}
        elif file_type == "EPUB":
            return {"text": "", "sections": _parse_epub(file_bytes)}
        elif file_type == "HTML":
            return {"text": _parse_html(file_bytes), "sections": []}
        elif file_type == "RTF":
            return {"text": _parse_rtf(file_bytes), "sections": []}
        elif file_type == "JSON":
            return {"text": _parse_json(file_bytes), "sections": []}
    except Exception as e:
        logger.error(f"Extraction failed for {file_type} ({filename}): {e}")
    return {"text": "", "sections": []}


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


def _parse_docx(file_bytes: bytes) -> list[dict]:
    import docx
    document = docx.Document(io.BytesIO(file_bytes))
    sections = []
    current_title = "Overview"
    current_lines = []
    for para in document.paragraphs:
        style = (para.style.name if para.style else "") or ""
        text = para.text.strip()
        if not text:
            continue
        if style.startswith("Heading") or style == "Title":
            _flush(current_title, current_lines, sections)
            current_title, current_lines = text, []
        else:
            current_lines.append(text)
    _flush(current_title, current_lines, sections)
    for i, table in enumerate(document.tables, start=1):
        rows_text = []
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                rows_text.append(" | ".join(cells))
        if rows_text:
            sections.append({"title": f"Table {i}", "body": "\n".join(rows_text)})
    return [s for s in sections if s["body"].strip()]


def _parse_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="ignore")


def _parse_epub(file_bytes: bytes) -> list[dict]:
    import ebooklib
    from ebooklib import epub
    from html.parser import HTMLParser
    import tempfile
    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
        def handle_data(self, data):
            if data.strip():
                self.parts.append(data.strip())
    # Write to temp file because some ebooklib versions don't support BytesIO
    fd, tmp_path = tempfile.mkstemp(suffix=".epub")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(file_bytes)
        book = epub.read_epub(tmp_path)
    except Exception:
        os.unlink(tmp_path)
        raise
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    sections = []
    for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT), start=1):
        parser = _TextExtractor()
        try:
            content_bytes = item.get_content()
            if content_bytes:
                parser.feed(content_bytes.decode("utf-8", errors="ignore"))
        except Exception:
            continue
        body = "\n".join(parser.parts).strip()
        if body:
            sections.append({"title": item.get_name() or f"Chapter {i}", "body": body})
    return sections


def _parse_html(file_bytes: bytes) -> str:
    from html.parser import HTMLParser
    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts = []
            self._skip = False
        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self._skip = True
        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self._skip = False
        def handle_data(self, data):
            if not self._skip and data.strip():
                self.parts.append(data.strip())
    parser = _TextExtractor()
    parser.feed(file_bytes.decode("utf-8", errors="ignore"))
    return "\n".join(parser.parts)


def _parse_rtf(file_bytes: bytes) -> str:
    from striprtf.striprtf import rtf_to_text
    return rtf_to_text(file_bytes.decode("utf-8", errors="ignore"))


def _parse_json(file_bytes: bytes) -> str:
    import json as _json
    data = _json.loads(file_bytes.decode("utf-8", errors="ignore"))
    return _json.dumps(data, indent=2, ensure_ascii=False)


def _parse_md(text: str) -> list[dict]:
    sections = []
    current_title = "Overview"
    current_lines = []
    for line in text.splitlines():
        stripped = line.lstrip("#").strip()
        if line.startswith("### "):
            _flush(current_title, current_lines, sections)
            current_title, current_lines = stripped, []
        elif line.startswith("## "):
            _flush(current_title, current_lines, sections)
            current_title, current_lines = stripped, []
        elif line.startswith("# "):
            _flush(current_title, current_lines, sections)
            current_title, current_lines = stripped, []
        else:
            current_lines.append(line)
    _flush(current_title, current_lines, sections)
    return [s for s in sections if s["body"].strip()]


def _flush(title: str, lines: list[str], out: list[dict]):
    body = "\n".join(lines).strip()
    if body:
        out.append({"title": title, "body": body})


def _table_to_markdown(headers: list[str], rows: list[list], max_rows: int = 100) -> str:
    """Convert tabular data to a markdown table string.
    
    For very large tables, only the first max_rows are included and a
    summary note is appended.
    """
    if not headers or not rows:
        return ""
    
    # Build header row
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join("---" for _ in headers) + " |\n"
    
    truncated = len(rows) > max_rows
    display_rows = rows[:max_rows]
    
    for row in display_rows:
        cells = [str(c) if c is not None else "" for c in row]
        md += "| " + " | ".join(cells) + " |\n"
    
    if truncated:
        md += f"\n*[Table truncated: {len(rows)} total rows, showing first {max_rows}]*\n"
    
    return md


def _generate_table_summary(title: str, headers: list[str], row_count: int, sheet_name: str = None) -> str:
    """Generate a natural-language summary of a table for the parent node body."""
    parts = [f"Spreadsheet: {title}"]
    if sheet_name:
        parts.append(f"Sheet: {sheet_name}")
    parts.append(f"Rows: {row_count}")
    parts.append(f"Columns: {', '.join(headers)}")
    return " | ".join(parts)


def _parse_csv(file_bytes: bytes, doc_title: str = "Untitled") -> list[dict]:
    """Parse CSV into a single table section + summary, not one node per row."""
    import csv, io as _io
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(_io.StringIO(text))
    
    rows = list(reader)
    if not rows:
        return []
    
    headers = list(rows[0].keys())
    total_rows = len(rows)
    
    if total_rows > _MAX_SPREADSHEET_ROWS:
        rows = rows[:_MAX_SPREADSHEET_ROWS]
        logger.warning(f"CSV truncated at {_MAX_SPREADSHEET_ROWS} rows")
    
    # Build markdown table
    md_rows = [[row.get(h, "") for h in headers] for row in rows]
    table_md = _table_to_markdown(headers, md_rows)
    
    # Generate summary
    summary = _generate_table_summary(doc_title, headers, total_rows)
    
    return [
        {"title": doc_title, "body": summary, "type": "table_summary"},
        {"title": f"{doc_title} - Data", "body": table_md, "type": "table_data"},
    ]


def _parse_xlsx(file_bytes: bytes, doc_title: str = "Untitled") -> list[dict]:
    """Parse Excel into one section per sheet (summary + data), not one node per row."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sections = []
    
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        
        headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]
        data_rows = rows[1:]
        total_rows = len(data_rows)
        
        if total_rows > _MAX_SPREADSHEET_ROWS:
            data_rows = data_rows[:_MAX_SPREADSHEET_ROWS]
            logger.warning(f"XLSX sheet '{sheet_name}' truncated at {_MAX_SPREADSHEET_ROWS} rows")
        
        # Build markdown table
        md_rows = [[str(c) if c is not None else "" for c in row] for row in data_rows]
        table_md = _table_to_markdown(headers, md_rows)
        
        # Generate summary
        summary = _generate_table_summary(doc_title, headers, total_rows, sheet_name)
        
        sections.append({
            "title": f"{doc_title} - {sheet_name}",
            "body": summary,
            "type": "table_summary",
        })
        sections.append({
            "title": f"{doc_title} - {sheet_name} - Data",
            "body": table_md,
            "type": "table_data",
        })
    
    wb.close()
    return sections


def _parse_svg(file_bytes: bytes) -> str:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(file_bytes)
    texts = []
    text_tags = {"title", "desc", "text", "tspan", "flowRoot", "flowPara"}
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local in text_tags:
            if elem.text and elem.text.strip():
                texts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                texts.append(elem.tail.strip())
    return "\n".join(dict.fromkeys(texts))
