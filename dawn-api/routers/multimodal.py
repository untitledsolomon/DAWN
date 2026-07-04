"""
v12.0 — Multi-Modal Capabilities
Image analysis, OCR, audio transcription, text-to-speech, video analysis
"""
import os
import json
import base64
import logging
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional
from config import settings as app_settings
import db.client as db

logger = logging.getLogger(__name__)
router = APIRouter()

def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ─── Schemas ──────────────────────────────────────────────────────────────

class ImageAnalysisRequest(BaseModel):
    image_base64: str
    prompt: str = "Describe this image in detail"

class TranscriptionResponse(BaseModel):
    text: str
    language: str = "en"
    duration_seconds: float = 0.0
    segments: list = []

class TTSRequest(BaseModel):
    text: str
    voice: str = "default"
    speed: float = 1.0

# ─── OCR / Image Analysis ─────────────────────────────────────────────────

@router.post("/multimodal/ocr", tags=["multimodal"])
async def ocr_image(
    file: UploadFile = File(...),
    _: None = Depends(verify_key),
):
    """Extract text from an image using OCR (Tesseract)."""
    try:
        import pytesseract
        from PIL import Image
        
        contents = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        try:
            img = Image.open(tmp_path)
            text = pytesseract.image_to_string(img)
            
            # Also get confidence data
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            
            return {
                "text": text.strip(),
                "word_count": len(text.split()),
                "confidence": sum(data.get("conf", [0])) / len(data.get("conf", [1])) if data.get("conf") else 0,
                "language": "eng",
            }
        finally:
            os.unlink(tmp_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="Tesseract OCR not installed. Run: pip install pytesseract Pillow")
    except Exception as e:
        logger.error(f"[multimodal] OCR failed: {e}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")


@router.post("/multimodal/analyze-image", tags=["multimodal"])
async def analyze_image(
    req: ImageAnalysisRequest,
    _: None = Depends(verify_key),
):
    """Analyze an image using the LLM (vision capabilities)."""
    try:
        from llm.engine import get_engine
        
        engine = get_engine()
        
        # Build a vision-capable message
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": req.prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{req.image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ]
        
        # Use the engine's complete method (may need to adapt for vision)
        response = await engine.complete(messages)
        
        return {
            "analysis": response,
            "model": engine.model_name if hasattr(engine, 'model_name') else "deepseek-vision",
        }
    except Exception as e:
        logger.error(f"[multimodal] Image analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Image analysis failed: {str(e)}")


@router.post("/multimodal/transcribe", tags=["multimodal"])
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form("en"),
    _: None = Depends(verify_key),
):
    """Transcribe audio using Whisper."""
    try:
        import whisper
        
        contents = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        try:
            model = whisper.load_model("base")
            result = model.transcribe(tmp_path, language=language)
            
            return TranscriptionResponse(
                text=result["text"].strip(),
                language=result.get("language", "en"),
                duration_seconds=result.get("duration", 0),
                segments=result.get("segments", []),
            )
        finally:
            os.unlink(tmp_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="Whisper not installed. Run: pip install openai-whisper")
    except Exception as e:
        logger.error(f"[multimodal] Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@router.post("/multimodal/tts", tags=["multimodal"])
async def text_to_speech(
    req: TTSRequest,
    _: None = Depends(verify_key),
):
    """Convert text to speech."""
    try:
        from TTS.api import TTS
        
        tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = tmp.name
        
        tts.tts_to_file(text=req.text, file_path=output_path)
        
        with open(output_path, "rb") as f:
            audio_base64 = base64.b64encode(f.read()).decode()
        
        os.unlink(output_path)
        
        return {
            "audio_base64": audio_base64,
            "format": "wav",
            "duration_seconds": len(req.text) / 15,  # rough estimate
        }
    except ImportError:
        raise HTTPException(status_code=501, detail="TTS not installed. Run: pip install TTS")
    except Exception as e:
        logger.error(f"[multimodal] TTS failed: {e}")
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")


@router.post("/multimodal/analyze-document", tags=["multimodal"])
async def analyze_document_layout(
    file: UploadFile = File(...),
    _: None = Depends(verify_key),
):
    """Analyze document layout (PDF, image) and extract structure."""
    try:
        import fitz  # PyMuPDF
        
        contents = await file.read()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name
        
        try:
            doc = fitz.open(tmp_path)
            pages = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                images = page.get_images()
                tables = page.find_tables()
                
                pages.append({
                    "page_number": page_num + 1,
                    "text_length": len(text),
                    "image_count": len(images),
                    "table_count": len(tables.tables) if tables else 0,
                    "text_preview": text[:500],
                })
            
            return {
                "page_count": len(doc),
                "pages": pages,
                "metadata": {
                    "title": doc.metadata.get("title", ""),
                    "author": doc.metadata.get("author", ""),
                    "subject": doc.metadata.get("subject", ""),
                },
            }
        finally:
            doc.close()
            os.unlink(tmp_path)
    except ImportError:
        raise HTTPException(status_code=501, detail="PyMuPDF not installed. Run: pip install pymupdf")
    except Exception as e:
        logger.error(f"[multimodal] Document analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Document analysis failed: {str(e)}")


@router.get("/multimodal/capabilities", tags=["multimodal"])
async def get_multimodal_capabilities(_: None = Depends(verify_key)):
    """Check which multi-modal capabilities are available."""
    capabilities = {
        "ocr": False,
        "image_analysis": False,
        "audio_transcription": False,
        "text_to_speech": False,
        "document_analysis": False,
    }
    
    try:
        import pytesseract
        capabilities["ocr"] = True
    except ImportError:
        pass
    
    try:
        from llm.engine import get_engine
        engine = get_engine()
        capabilities["image_analysis"] = hasattr(engine, 'supports_vision') and engine.supports_vision
    except Exception:
        pass
    
    try:
        import whisper
        capabilities["audio_transcription"] = True
    except ImportError:
        pass
    
    try:
        from TTS.api import TTS
        capabilities["text_to_speech"] = True
    except ImportError:
        pass
    
    try:
        import fitz
        capabilities["document_analysis"] = True
    except ImportError:
        pass
    
    return capabilities
