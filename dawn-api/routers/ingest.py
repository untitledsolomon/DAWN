from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db
import logging
import io
import os

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Supported file types ──────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    ".pdf":      "PDF",
    ".md":       "Markdown",
    ".markdown": "Markdown",
    ".csv":      "CSV",
    ".xlsx":     "Excel",
    ".xls":      "Excel",
    ".svg":      "SVG",
}


def detect_file_type(filename: str) -> Optional[str]:
    ext = os.path.splitext(filename.lower())[1]
    return SUPPORTED_EXTENSIONS.get(ext)


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
    Accepts: PDF, Markdown (.md), CSV, Excel (.xlsx/.xls), SVG.
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
            detail=f"Unsupported file type '{ext}'. Supported: PDF, MD, CSV, XLSX, SVG",
        )

    file_bytes = await file.read()
    doc_title = title.strip() or os.path.splitext(filename)[0]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Extract content synchronously so errors surface before we return
    extraction = _extract_content(file_bytes, file_type, filename)

    has_sections = bool(extraction.get("sections"))
    has_text = bool(extraction.get("text", "").strip())

    if not has_sections and not has_text:
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract content from {file_type} file. "
                   f"{'PDF may be scanned/image-only.' if file_type == 'PDF' else 'File may be empty or corrupted.'}",
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
    except Exception as e:
        logger.error(f"Extraction failed for {file_type} ({filename}): {e}")
    return {"text": "", "sections": []}


def _parse_pdf(file_bytes: bytes) -> str:
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    return "\n\n".join(pages)


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


async def _run_repo_ingest(req: RepoIngestRequest):
    from ingestion.repo import ingest_repo
    try:
        result = await ingest_repo(req.repo_path, req.repo_name, req.tags)
        await db.log_ingestion({
            "source": "repo",
            "source_ref": req.repo_path,
            "nodes_created": result["nodes_created"],
            "edges_created": result["edges_created"],
            "status": "success",
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
