"""
Explainer router — generates, validates, stores, and regenerates animated
whiteboard-style explainer HTML artifacts for math and conceptual topics.

Endpoints:
  POST /explainer/generate   — generate a new explainer from a topic
  POST /explainer/regenerate — regenerate an existing explainer with a follow-up
  GET  /explainer/{id}       — fetch a stored explainer artifact
"""
import json
import logging
import re
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
from llm.engine import get_engine, build_messages
from tools.explainer import (
    ExplainerTool,
    validate_explainer_fragment,
    EXPLAINER_SYSTEM_PROMPT,
    VALID_DIAGRAM_TYPES,
)
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth ───────────────────────────────────────────────────────────────────

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Schema ─────────────────────────────────────────────────────────────────

class ExplainerGenerateRequest(BaseModel):
    topic: str
    diagram_type: str = "illustrative"
    title: Optional[str] = None
    description: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None


class ExplainerRegenerateRequest(BaseModel):
    artifact_id: str
    follow_up: str
    session_id: Optional[str] = None


class ExplainerResponse(BaseModel):
    id: str
    type: str = "explainer"
    title: str
    code: str
    prompt: str
    metadata: dict
    created_at: str


# ── LLM call helper ────────────────────────────────────────────────────────

async def _call_llm_for_explainer(
    topic: str,
    diagram_type: str,
    existing_code: Optional[str] = None,
    follow_up: Optional[str] = None,
) -> tuple[str, str]:
    """Call the LLM to generate an explainer HTML fragment.
    Returns (html_fragment, full_prompt) on success.
    Raises HTTPException on failure."""
    engine = get_engine()

    # Build the user prompt
    diagram_guide = {
        "flowchart": "Create a flowchart-style animation showing sequential steps and decision branches.",
        "structural": "Create a structural diagram showing containment, architecture, and relationships.",
        "illustrative": "Create an illustrative visual metaphor that builds intuition about the concept.",
    }

    user_prompt_parts = [f"Topic: {topic}"]
    user_prompt_parts.append(f"Diagram type: {diagram_type}")
    user_prompt_parts.append(f"Style guide: {diagram_guide.get(diagram_type, diagram_guide['illustrative'])}")

    if existing_code and follow_up:
        user_prompt_parts.append(f"\n\n--- EXISTING EXPLAINER CODE ---\n{existing_code}\n--- END EXISTING CODE ---")
        user_prompt_parts.append(f"\nFollow-up instruction: {follow_up}")
        user_prompt_parts.append("\nModify the existing code according to the follow-up instruction. Return the COMPLETE updated HTML fragment, not just the changes.")
    else:
        user_prompt_parts.append("\nGenerate a complete, self-contained HTML fragment following all constraints below.")

    user_prompt = "\n".join(user_prompt_parts)

    messages = [
        {"role": "system", "content": EXPLAINER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await engine.complete(messages)
    except Exception as e:
        logger.error(f"[explainer] LLM call failed: {e}")
        raise HTTPException(status_code=502, detail=f"LLM generation failed: {e}")

    # Strip any markdown fences the LLM might add
    html = response.strip()
    # Remove ```html ... ``` fences
    html = re.sub(r'^```(?:html)?\s*\n', '', html)
    html = re.sub(r'\n```\s*$', '', html)
    html = html.strip()

    return html, user_prompt


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/generate")
async def generate_explainer(
    req: ExplainerGenerateRequest,
    _: None = Depends(verify_key),
):
    """Generate a new explainer artifact from a topic."""
    if req.diagram_type not in VALID_DIAGRAM_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid diagram_type '{req.diagram_type}'. Must be one of: {', '.join(sorted(VALID_DIAGRAM_TYPES))}",
        )

    title = req.title or f"Explainer: {req.topic[:60]}"

    # Try generation with up to 1 retry on validation failure
    html = None
    last_error = None
    for attempt in range(2):  # max 1 retry
        try:
            html, prompt_used = await _call_llm_for_explainer(
                topic=req.topic,
                diagram_type=req.diagram_type,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[explainer] Generation attempt {attempt+1} failed: {e}")
            last_error = str(e)
            continue

        # Validate
        is_valid, error_msg = validate_explainer_fragment(html)
        if is_valid:
            last_error = None
            break
        else:
            logger.warning(f"[explainer] Validation failed (attempt {attempt+1}): {error_msg}")
            last_error = error_msg
            html = None
            continue

    if html is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate valid explainer after retry. Last error: {last_error}",
        )

    # Persist to Supabase
    try:
        supabase = db.get_db()
        data = {
            "session_id": req.session_id,
            "type": "explainer",
            "title": title,
            "code": html,
            "prompt": prompt_used,
            "metadata": {
                "diagram_type": req.diagram_type,
                "topic": req.topic,
                "model_used": settings.deepseek_model,
            },
        }
        if req.description:
            data["description"] = req.description
        if req.conversation_id:
            data["conversation_id"] = req.conversation_id
        if req.user_id:
            data["user_id"] = req.user_id

        res = supabase.table("artifacts").insert(data).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to store explainer artifact")
        artifact = res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[explainer] Failed to persist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to store explainer: {e}")

    return ExplainerResponse(
        id=artifact["id"],
        title=artifact["title"],
        code=artifact["code"],
        prompt=artifact["prompt"],
        metadata=artifact.get("metadata", {}),
        created_at=artifact["created_at"],
    )


@router.post("/regenerate")
async def regenerate_explainer(
    req: ExplainerRegenerateRequest,
    _: None = Depends(verify_key),
):
    """Regenerate an existing explainer with a follow-up instruction."""
    # Fetch existing artifact
    try:
        supabase = db.get_db()
        res = supabase.table("artifacts").select("*").eq("id", req.artifact_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Artifact not found")
        existing = res.data[0]
        if existing.get("type") != "explainer":
            raise HTTPException(status_code=400, detail="Artifact is not an explainer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[explainer] Failed to fetch artifact {req.artifact_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch existing artifact")

    existing_code = existing.get("code", "")
    existing_prompt = existing.get("prompt", "")
    existing_metadata = existing.get("metadata", {}) or {}

    # Generate updated version
    html = None
    last_error = None
    for attempt in range(2):
        try:
            html, _ = await _call_llm_for_explainer(
                topic=existing_metadata.get("topic", "unknown"),
                diagram_type=existing_metadata.get("diagram_type", "illustrative"),
                existing_code=existing_code,
                follow_up=req.follow_up,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[explainer] Regeneration attempt {attempt+1} failed: {e}")
            last_error = str(e)
            continue

        is_valid, error_msg = validate_explainer_fragment(html)
        if is_valid:
            last_error = None
            break
        else:
            logger.warning(f"[explainer] Regeneration validation failed (attempt {attempt+1}): {error_msg}")
            last_error = error_msg
            html = None
            continue

    if html is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to regenerate valid explainer after retry. Last error: {last_error}",
        )

    # Update in DB
    try:
        supabase = db.get_db()
        updated_prompt = f"{existing_prompt}\n\n--- FOLLOW-UP ---\n{req.follow_up}"
        updated_metadata = {**existing_metadata, "regenerated": True, "follow_up": req.follow_up}
        res = supabase.table("artifacts").update({
            "code": html,
            "prompt": updated_prompt,
            "metadata": updated_metadata,
        }).eq("id", req.artifact_id).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to update explainer artifact")
        artifact = res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[explainer] Failed to update artifact {req.artifact_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update explainer")

    return ExplainerResponse(
        id=artifact["id"],
        title=artifact["title"],
        code=artifact["code"],
        prompt=artifact["prompt"],
        metadata=artifact.get("metadata", {}),
        created_at=artifact["created_at"],
    )


@router.get("/{artifact_id}")
async def get_explainer(
    artifact_id: str,
    _: None = Depends(verify_key),
):
    """Fetch a stored explainer artifact by ID."""
    try:
        supabase = db.get_db()
        res = supabase.table("artifacts").select("*").eq("id", artifact_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Artifact not found")
        artifact = res.data[0]
        if artifact.get("type") != "explainer":
            raise HTTPException(status_code=400, detail="Artifact is not an explainer")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[explainer] Failed to fetch {artifact_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch explainer")

    return ExplainerResponse(
        id=artifact["id"],
        title=artifact["title"],
        code=artifact["code"],
        prompt=artifact["prompt"],
        metadata=artifact.get("metadata", {}),
        created_at=artifact["created_at"],
    )
