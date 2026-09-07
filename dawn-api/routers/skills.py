"""
Skills API — list installed skills and install new ones.

Skills are installed via the same logic the agent uses (skills/installer.py
and skills/ecc_installer.py). This exposes it over HTTP so the UI can show
installed skills and trigger installs by name or repo URL.
"""
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
from tools.registry import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class SkillInstallRequest(BaseModel):
    repo_url: str


class ECCSkillInstallRequest(BaseModel):
    skill_name: str


def _skills_dir() -> Path:
    root = getattr(settings, "skills_install_root", None) or "./installed_skills"
    path = Path(root).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@router.get("/skills", tags=["skills"])
async def list_skills(_: None = Depends(verify_key)):
    """List installed skills (from the registry + install dir)."""
    registry = get_registry()
    tools = registry.list_tools()
    skills = []
    for t in tools:
        if t.name.startswith("skill_"):
            skills.append({
                "name": t.name,
                "description": getattr(t, "description", ""),
                "type": "knowledge" if "[Knowledge skill]" in getattr(t, "description", "") else "container",
            })
    # Also list skill dirs on disk that may not be registered yet.
    skills_dir = _skills_dir()
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and not any(s["name"] == f"skill_{d.name}" for s in skills):
                skills.append({"name": f"skill_{d.name}", "description": "", "type": "installed"})
    return skills


@router.post("/skills/install", tags=["skills"])
async def install_skill(req: SkillInstallRequest, _: None = Depends(verify_key)):
    """Install a skill from a repo URL or raw file link."""
    try:
        from skills.installer import SkillInstallTool
        tool = SkillInstallTool()
        result = await tool.run(req.repo_url)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return result.output if isinstance(result.output, dict) else {"message": result.output}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills/install-ecc", tags=["skills"])
async def install_ecc_skill(req: ECCSkillInstallRequest, _: None = Depends(verify_key)):
    """Install a skill from the ECC library by name."""
    try:
        from skills.ecc_installer import InstallECCSkillTool
        tool = InstallECCSkillTool()
        result = await tool.run(req.skill_name)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return result.output if isinstance(result.output, dict) else {"message": result.output}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/ecc", tags=["skills"])
async def list_ecc_skills(query: str = "", _: None = Depends(verify_key)):
    """List available ECC library skills (optionally filtered)."""
    try:
        from skills.ecc_installer import ListECCSkillsTool
        tool = ListECCSkillsTool()
        result = await tool.run(query=query, limit=200)
        if not result.success:
            return {"skills": [], "count": 0, "note": result.error}
        return result.output
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
