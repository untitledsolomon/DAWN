from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db
import logging
import asyncio
import io
import os
import zipfile

logger = logging.getLogger(__name__)
router = APIRouter()

_tesseract_configured = False


def _ensure_tesseract_configured():
    """
    Point pytesseract at an explicit binary path if TESSERACT_CMD is set
    (see config.py) — mainly for Windows dev machines where PATH
    resolution for a freshly-installed binary is unreliable across shells
    and requires a new terminal session to pick up. On Linux (VPS, where
    tesseract-ocr is apt-installed onto PATH directly) this is a no-op:
    leave TESSERACT_CMD unset and pytesseract finds it on PATH as normal.
    Idempotent — safe to call before every OCR attempt.
    """
    global _tesseract_configured
    if _tesseract_configured:
        return
    if settings.tesseract_cmd:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        logger.info(f"pytesseract configured to use explicit binary: {settings.tesseract_cmd}")
    _tesseract_configured = True

# ── Supported file types ──────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".pdf":      "PDF",
    ".md":       "Markdown",
    ".markdown": "Markdown",
    ".csv":      "CSV",
    ".xlsx":     "Excel",
    ".xls":      "Excel",
    ".svg":      "SVG",
    ".docx":     "Word",
    ".txt":      "Text",
    ".epub":     "EPUB",
    ".html":     "HTML",
    ".htm":      "HTML",
    ".rtf":      "RTF",
    ".json":     "JSON",
}

# Files this large are extracted in the background instead of inline,
# so an upload of a huge book/PDF doesn't block the HTTP request thread
# or risk a request timeout. Small files still extract synchronously so
# bad/empty uploads fail fast with a useful error.
_INLINE_EXTRACTION_MAX_BYTES = 15 * 1024 * 1024  # 15 MB

# Hard ceiling on any single upload regardless of type — stops absurdly
# large uploads (e.g. someone renaming a 5GB file to .txt) from ever
# reaching an extractor at all.
_MAX_UPLOAD_BYTES = 250 * 1024 * 1024  # 250 MB

# docx/epub/xlsx are zip containers. A malicious or corrupt archive can
# claim a tiny compressed size but expand to gigabytes when unzipped
# ("zip bomb"). We check the archive's *declared* uncompressed size
# before asking docx/epub/openpyxl libraries to actually decompress it.
_MAX_ZIP_UNCOMPRESSED_BYTES = 300 * 1024 * 1024  # 300 MB
_MAX_ZIP_COMPRESSION_RATIO = 100  # uncompressed/compressed above this is suspicious

# Caps how many large-file ingests can run in the background at once,
# so e.g. two 200MB PDFs uploaded back-to-back don't both start
# extracting simultaneously and compete for all CPU/RAM on the VPS.
_LARGE_INGEST_CONCURRENCY = 2
_large_ingest_semaphore = asyncio.Semaphore(_LARGE_INGEST_CONCURRENCY)


def detect_file_type(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename.lower())[1]
    return SUPPORTED_EXTENSIONS.get(ext)


def _check_zip_safety(file_bytes: bytes) -> Optional[str]:
    """
    Inspect a zip-based container (docx/epub/xlsx) for zip-bomb signatures
    without fully decompressing it. Returns an error string if unsafe,
    None if OK.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        return "File is not a valid zip-based document (corrupt or not actually this format)."

    total_uncompressed = 0
    for info in zf.infolist():
        total_uncompressed += info.file_size
        if info.file_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
            return f"Archive contains a member that expands to over {_MAX_ZIP_UNCOMPRESSED_BYTES // (1024*1024)}MB — refusing to decompress."
        if info.compress_size > 0:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > _MAX_ZIP_COMPRESSION_RATIO and info.file_size > 10_000_000:
                return "Archive has a suspiciously high compression ratio (possible zip bomb) — refusing to decompress."

    if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
        return f"Archive expands to over {_MAX_ZIP_UNCOMPRESSED_BYTES // (1024*1024)}MB total — refusing to decompress."

    return None


# ── Auth ──────────────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Request schemas ───────────────────────────────────────────────────────────

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


# ── Existing endpoints ────────────────────────────────────────────────────────

@router.post("/repo")
async def ingest_repo(
    req: RepoIngestRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    background_tasks.add_task(_run_repo_ingest, req)
    return {"status": "queued", "repo": req.repo_name}


@router.post("/document")
async def ingest_document(
    req: DocumentIngestRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    background_tasks.add_task(_run_doc_ingest, req)
    return {"status": "queued", "title": req.title}


@router.post("/memory")
async def ingest_memory(
    req: MemoryIngestRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(verify_key),
):
    background_tasks.add_task(_run_memory_ingest, req)
    return {"status": "queued"}


# ── Unified file upload endpoint ──────────────────────────────────────────────

@router.post("/file")
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(""),
    tags: str = Form(""),
    x_api_key: Optional[str] = Header(None),
):
    """
    Unified file ingestion endpoint.
    Accepts: PDF, Markdown, TXT, CSV, Excel, SVG, Word (.docx), EPUB, HTML, RTF, JSON.
    File type is detected automatically from the extension.
    """
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    filename = file.filename or ""
    file_type = detect_file_type(filename)

    if not file_type:
        ext = os.path.splitext(filename.lower())[1]
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(set(SUPPORTED_EXTENSIONS.values())))}",
        )

    file_bytes = await file.read()

    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is {len(file_bytes) / 1_000_000:.0f}MB, which exceeds the "
                   f"{_MAX_UPLOAD_BYTES // (1024*1024)}MB upload limit.",
        )

    # docx/epub/xlsx are zip containers — check declared uncompressed size
    # and compression ratio before any library tries to decompress them,
    # so a malicious or corrupt archive can't blow up memory/disk.
    if file_type in ("Word", "EPUB", "Excel"):
        zip_error = _check_zip_safety(file_bytes)
        if zip_error:
            raise HTTPException(status_code=422, detail=zip_error)

    doc_title = title.strip() or os.path.splitext(filename)[0]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    if len(file_bytes) > _INLINE_EXTRACTION_MAX_BYTES:
        # Large file: do a cheap sanity check now (fail fast on garbage
        # uploads) but defer the actual extraction + ingestion to the
        # background task so we don't hold the request thread or the
        # whole extracted text in memory during the HTTP request.
        if not _quick_sanity_check(file_bytes, file_type):
            raise HTTPException(
                status_code=422,
                detail=f"File does not look like a valid {file_type} file.",
            )

        background_tasks.add_task(
            _run_large_file_ingest,
            doc_title,
            filename,
            file_type,
            file_bytes,
            tag_list,
        )

        return {
            "status": "queued",
            "title": doc_title,
            "file_type": file_type,
            "filename": filename,
            "note": f"Large file ({len(file_bytes) / 1_000_000:.1f} MB) — "
                    f"extracting and ingesting in the background. Check the "
                    f"ingestion log for progress.",
        }

    # Small/normal file: extract synchronously so errors surface before we
    # return. Wrapped defensively — a malformed file with a "correct"
    # extension (e.g. a renamed binary saved as .txt/.json) must produce
    # a clean 422, not an unhandled 500.
    try:
        extraction = _extract_content(file_bytes, file_type, filename)
    except Exception as e:
        logger.error(f"Unexpected extraction failure for {file_type} ({filename}): {e}")
        raise HTTPException(
            status_code=422,
            detail=f"File could not be parsed as {file_type} — it may be corrupted, "
                   f"password-protected, or mislabeled.",
        )

    has_sections = bool(extraction.get("sections"))
    has_text = bool(extraction.get("text", "").strip())

    if not has_sections and not has_text:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract content from {file_type} file. "
                   f"{'PDF may be scanned/image-only — OCR fallback was attempted and also found no text.' if file_type == 'PDF' else 'File may be empty or corrupted.'}",
        )

    background_tasks.add_task(
        _run_file_ingest,
        doc_title,
        filename,
        file_type,
        extraction,
        tag_list,
    )

    section_count = len(extraction.get("sections", []))
    word_count = sum(len(s["body"].split()) for s in extraction.get("sections", [])) or \
                 len(extraction.get("text", "").split())

    return {
        "status": "queued",
        "title": doc_title,
        "file_type": file_type,
        "filename": filename,
        "sections": section_count,
        "word_count": word_count,
    }


def _quick_sanity_check(file_bytes: bytes, file_type: str) -> bool:
    """Cheap magic-byte / structure check for large uploads, without fully parsing them."""
    try:
        if file_type == "PDF":
            return file_bytes[:5] == b"%PDF-"
        if file_type == "Word":
            return file_bytes[:2] == b"PK"  # docx is a zip container
        if file_type == "EPUB":
            return file_bytes[:2] == b"PK"
        return True
    except Exception:
        return False


# ── Parsers ───────────────────────────────────────────────────────────────────

def _extract_content(file_bytes: bytes, file_type: str, filename: str) -> dict:
    """Route to the right parser. Returns {"text": str, "sections": list[dict]}"""
    try:
        if file_type == "PDF":
            return {"text": _parse_pdf(file_bytes), "sections": []}
        elif file_type == "Markdown":
            return {"text": "", "sections": _parse_md(file_bytes.decode("utf-8", errors="ignore"))}
        elif file_type == "CSV":
            return {"text": "", "sections": _parse_csv(file_bytes)}
        elif file_type == "Excel":
            return {"text": "", "sections": _parse_xlsx(file_bytes)}
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
    """
    Extract text using PyMuPDF (fitz), non-streaming variant for small/
    normal-sized PDFs. Handles complex book layouts (columns, drop caps,
    stylized fonts) far better than PyPDF2, which tends to emit near-empty
    or garbled fragments (e.g. "I\\nI\\nr") on that kind of typography.

    Falls back to OCR (Tesseract via pytesseract) if the direct text
    layer comes back empty/near-empty — i.e. a scanned/image-only PDF —
    since otherwise those silently produce no usable content at all.

    For very large PDFs, use iter_pdf_pages() instead — see _run_large_file_ingest.
    """
    result = "\n\n".join(iter_pdf_pages(file_bytes))

    if len(result.strip()) < 20:
        logger.warning(
            "PDF text layer returned near-empty content "
            f"({len(result.strip())} chars) — likely scanned/image-only. "
            "Attempting OCR fallback."
        )
        ocr_result = _ocr_pdf(file_bytes)
        if len(ocr_result.strip()) > len(result.strip()):
            return ocr_result

    return result


def _ocr_pdf(file_bytes: bytes, max_pages: int = 300) -> str:
    """
    OCR fallback for scanned PDFs with no text layer. Rasterizes each page
    to an image via PyMuPDF and runs Tesseract on it.

    Capped at max_pages: OCR is orders of magnitude slower than direct
    text extraction (roughly 1-3 seconds/page), so an uncapped run on a
    huge scanned book could tie up the background worker for a very long
    time. Pages beyond the cap are skipped with a note appended, rather
    than silently truncating without saying so.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR fallback unavailable — pytesseract/Pillow not installed.")
        return ""

    _ensure_tesseract_configured()

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text = []
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages)

    try:
        for i in range(pages_to_process):
            page = doc[i]
            # 2x zoom improves OCR accuracy on typical book-scan DPI
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(img)
            if text and text.strip():
                pages_text.append(text.strip())
    except Exception as e:
        logger.error(f"OCR fallback failed partway through: {e}")
    finally:
        doc.close()

    if total_pages > max_pages:
        pages_text.append(
            f"[OCR truncation notice: this PDF has {total_pages} pages; "
            f"only the first {max_pages} were OCR'd due to processing time limits.]"
        )

    return "\n\n".join(pages_text)


def iter_pdf_pages(file_bytes: bytes):
    """
    Yield extracted text one page at a time instead of building the whole
    document as one string. This is what makes arbitrarily large PDFs
    (hypothetically tens of thousands of pages) safe to ingest: memory use
    stays bounded by a single page's text, not the entire book.
    """
    import fitz  # pymupdf

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for page in doc:
            text = page.get_text("text")
            if text and text.strip():
                yield text.strip()
    finally:
        doc.close()


def _parse_docx(file_bytes: bytes) -> list[dict]:
    """Split a Word doc into sections on heading paragraphs (Heading 1/2/3 styles)."""
    import docx  # python-docx

    document = docx.Document(io.BytesIO(file_bytes))
    sections: list[dict] = []
    current_title = "Overview"
    current_lines: list[str] = []

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

    # Tables often carry real content in Word docs — pull them in too
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
    """Extract each chapter/spine item of an EPUB as its own section."""
    import ebooklib
    from ebooklib import epub
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data):
            if data.strip():
                self.parts.append(data.strip())

    book = epub.read_epub(io.BytesIO(file_bytes))
    sections: list[dict] = []

    for i, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT), start=1):
        parser = _TextExtractor()
        try:
            parser.feed(item.get_content().decode("utf-8", errors="ignore"))
        except Exception:
            continue
        body = "\n".join(parser.parts).strip()
        if body:
            chapter_title = item.get_name() or f"Chapter {i}"
            sections.append({"title": chapter_title, "body": body})

    return sections


def _parse_html(file_bytes: bytes) -> str:
    """Strip tags, keep readable text. Good enough for saved articles/pages."""
    from html.parser import HTMLParser

    class _TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
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
    """Split markdown into sections on headings. Each heading → one node."""
    sections: list[dict] = []
    current_title = "Overview"
    current_lines: list[str] = []

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


def _parse_csv(file_bytes: bytes) -> list[dict]:
    import csv
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    sections: list[dict] = []

    for i, row in enumerate(reader):
        if i >= 500:
            sections.append({
                "title": "Truncation notice",
                "body": f"CSV had more than 500 rows. Only the first 500 were ingested.",
            })
            break
        if not any(row.values()):
            continue
        first_val = next((v for v in row.values() if v), f"Row {i + 1}")
        title = str(first_val)[:80]
        body = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
        sections.append({"title": title, "body": body})

    return sections


def _parse_xlsx(file_bytes: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    sections: list[dict] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(rows[0])]

        # Sheet summary node
        sections.append({
            "title": f"Sheet: {sheet_name}",
            "body": f"Excel sheet '{sheet_name}' with {len(rows) - 1} rows and columns: {', '.join(headers)}",
        })

        for i, row in enumerate(rows[1:], start=1):
            if i > 500:
                sections.append({
                    "title": f"{sheet_name} — truncation notice",
                    "body": "Sheet had more than 500 rows. Only the first 500 were ingested.",
                })
                break
            if not any(r is not None for r in row):
                continue
            first_val = next((str(v) for v in row if v is not None), f"Row {i}")
            title = f"{sheet_name} — {first_val[:60]}"
            body = " | ".join(f"{h}: {v}" for h, v in zip(headers, row) if v is not None)
            sections.append({"title": title, "body": body})

    wb.close()
    return sections


def _parse_svg(file_bytes: bytes) -> str:
    """Extract human-readable text from SVG — labels, titles, descriptions."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(file_bytes)
    texts: list[str] = []
    text_tags = {"title", "desc", "text", "tspan", "flowRoot", "flowPara"}

    for elem in root.iter():
        # Strip namespace prefix for comparison
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local in text_tags:
            if elem.text and elem.text.strip():
                texts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                texts.append(elem.tail.strip())

    return "\n".join(dict.fromkeys(texts))  # deduplicate while preserving order


# ── Background workers ────────────────────────────────────────────────────────

async def _run_file_ingest(
    title: str,
    source_ref: str,
    file_type: str,
    extraction: dict,
    tags: list[str],
):
    from ingestion.repo import ingest_document, ingest_sections
    try:
        if extraction.get("sections"):
            result = await ingest_sections(title, extraction["sections"], source_ref, tags)
        else:
            result = await ingest_document(title, extraction["text"], source_ref, tags)

        await db.log_ingestion({
            "source": "document",
            "source_ref": source_ref,
            "nodes_created": result["nodes_created"],
            "edges_created": result.get("edges_created", 0),
            "status": "success",
        })
    except Exception as e:
        logger.error(f"File ingest failed ({file_type}): {e}")
        await db.log_ingestion({
            "source": "document",
            "source_ref": source_ref,
            "status": "failed",
            "error": str(e),
        })


async def _run_large_file_ingest(
    title: str,
    source_ref: str,
    file_type: str,
    file_bytes: bytes,
    tags: list[str],
):
    """
    Background ingestion path for large files. Streams content into the
    DB in batches rather than extracting everything into one in-memory
    string first — this is what makes an arbitrarily large PDF (or other
    large document) safe to ingest without blowing up memory.

    Concurrency is capped via _large_ingest_semaphore so multiple large
    uploads queued close together don't all extract simultaneously and
    starve the VPS of CPU/RAM.
    """
    async with _large_ingest_semaphore:
        from ingestion.repo import ingest_document_stream, ingest_sections

        try:
            if file_type == "PDF":
                # Peek at the first few pages to decide direct-extraction vs
                # OCR before committing to a strategy for the whole document
                # — cheaper than running full OCR speculatively on every PDF.
                sample_text = "".join(_peek_pdf_pages(file_bytes, sample_pages=5))
                if len(sample_text.strip()) < 20:
                    logger.warning(
                        f"Large PDF '{source_ref}' looks scanned/image-only "
                        f"(no text in first 5 pages) — using OCR page stream."
                    )
                    result = await ingest_document_stream(
                        title, _iter_ocr_pdf_pages(file_bytes), source_ref, tags,
                    )
                else:
                    result = await ingest_document_stream(
                        title, iter_pdf_pages(file_bytes), source_ref, tags,
                    )
            elif file_type == "Word":
                sections = _parse_docx(file_bytes)
                result = await ingest_sections(title, sections, source_ref, tags)
            elif file_type == "EPUB":
                sections = _parse_epub(file_bytes)
                result = await ingest_sections(title, sections, source_ref, tags)
            else:
                extraction = _extract_content(file_bytes, file_type, source_ref)
                if extraction.get("sections"):
                    result = await ingest_sections(title, extraction["sections"], source_ref, tags)
                else:
                    from ingestion.repo import ingest_document
                    result = await ingest_document(title, extraction["text"], source_ref, tags)

            await db.log_ingestion({
                "source": "document",
                "source_ref": source_ref,
                "nodes_created": result["nodes_created"],
                "edges_created": result.get("edges_created", 0),
                "status": "success",
            })
        except Exception as e:
            # Broad catch is intentional here: this runs unattended in the
            # background with no request to return an error to, so a
            # malformed/corrupt large file must not crash the worker or
            # vanish silently — it must land in the ingestion log.
            logger.error(f"Large file ingest failed ({file_type}, {source_ref}): {e}")
            await db.log_ingestion({
                "source": "document",
                "source_ref": source_ref,
                "status": "failed",
                "error": str(e)[:2000],
            })


def _peek_pdf_pages(file_bytes: bytes, sample_pages: int = 5):
    """Extract text from just the first few pages, to cheaply decide if OCR is needed."""
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        for i in range(min(sample_pages, len(doc))):
            text = doc[i].get_text("text")
            if text:
                yield text
    finally:
        doc.close()


def _iter_ocr_pdf_pages(file_bytes: bytes, max_pages: int = 2000):
    """
    Stream OCR'd page text one page at a time for large scanned PDFs,
    so — same as iter_pdf_pages — memory use stays bounded to one page
    at a time rather than holding the whole OCR'd book in memory.

    max_pages is much higher here than _ocr_pdf's inline-path cap (300)
    since this only runs in the background where a long-running OCR job
    doesn't block a request or a human waiting on a response — but it's
    still capped so a genuinely unbounded/corrupt PDF can't run forever.
    """
    try:
        import fitz
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.warning("OCR fallback unavailable — pytesseract/Pillow not installed.")
        return

    _ensure_tesseract_configured()

    doc = fitz.open(stream=file_bytes, filetype="pdf")
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
                # One bad page (corrupt image stream, etc.) shouldn't kill
                # the whole OCR run — skip it and keep going.
                logger.warning(f"OCR failed on page {i}: {e}")
                continue
    finally:
        doc.close()

    if total_pages > max_pages:
        yield (
            f"[OCR truncation notice: this PDF has {total_pages} pages; "
            f"only the first {max_pages} were OCR'd due to processing time limits.]"
        )


async def _run_repo_ingest(req: RepoIngestRequest):
    from ingestion.repo import ingest_repo
    try:
        result = await ingest_repo(req.repo_path, req.repo_name, req.tags)
        archived = result.get("nodes_archived", 0)
        status = "partial" if result.get("truncated") else "success"
        await db.log_ingestion({
            "source": "repo",
            "source_ref": req.repo_path,
            "nodes_created": result["nodes_created"],
            "edges_created": result["edges_created"],
            "status": status,
            "error": (
                f"Archived {archived} node(s) from a prior ingest of this repo. "
                + (f"Hit MAX_REPO_FILES limit after {result.get('files_processed')} files — "
                   f"repo may be larger than what was ingested." if result.get("truncated") else "")
            ) if archived or result.get("truncated") else None,
        })
    except Exception as e:
        logger.error(f"Repo ingest failed: {e}")
        await db.log_ingestion({
            "source": "repo",
            "source_ref": req.repo_path,
            "status": "failed",
            "error": str(e),
        })


async def _run_doc_ingest(req: DocumentIngestRequest):
    from ingestion.repo import ingest_document
    try:
        result = await ingest_document(req.title, req.content, req.source_ref, req.tags)
        await db.log_ingestion({
            "source": "document",
            "source_ref": req.source_ref or req.title,
            "nodes_created": result["nodes_created"],
            "edges_created": result.get("edges_created", 0),
            "status": "success",
        })
    except Exception as e:
        logger.error(f"Doc ingest failed: {e}")
        await db.log_ingestion({
            "source": "document",
            "source_ref": req.title,
            "status": "failed",
            "error": str(e),
        })


async def _run_memory_ingest(req: MemoryIngestRequest):
    from ingestion.memory import ingest_memory
    try:
        result = await ingest_memory(req.conversation, req.session_source)
        await db.log_ingestion({
            "source": "conversation",
            "source_ref": req.session_source,
            "nodes_created": result["nodes_created"],
            "status": "success",
        })
    except Exception as e:
        logger.error(f"Memory ingest failed: {e}")
        await db.log_ingestion({
            "source": "conversation",
            "source_ref": req.session_source,
            "status": "failed",
            "error": str(e),
        })


@router.get("/log")
async def get_log(_: None = Depends(verify_key)):
    return await db.get_ingestion_log()
