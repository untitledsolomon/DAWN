"""
Runtime settings API + tool inventory. Same verify_key auth as routers/settings.py.
The Settings UI is generated from the metadata returned here.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from config import settings as app_settings
from runtime_settings.registry import SETTING_DEFS, SettingDef
from runtime_settings.store import get_runtime

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != app_settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class SetBody(BaseModel):
    value: Any
    reason: Optional[str] = None


def _env_value(d: SettingDef):
    if d.env:
        return getattr(app_settings, d.env, None)
    return None


def _meta(d: SettingDef, runtime, override_row: Optional[dict]) -> dict:
    src = "default"
    if d.key in runtime._overrides:
        src = "db"
    elif d.env and getattr(app_settings, d.env, None) is not None:
        src = "env"
    return {
        "key": d.key,
        "label": d.label,
        "description": d.description,
        "group": d.group,
        "type": d.type,
        "min": d.min,
        "max": d.max,
        "step": d.step,
        "choices": list(d.choices or ()),
        "unit": d.unit,
        "default": d.default,
        "env_value": _env_value(d),
        "value": runtime.get(d.key),
        "source": src,
        "hot": d.hot,
        "advanced": d.advanced,
        "updated_by": (override_row or {}).get("updated_by"),
        "updated_at": (override_row or {}).get("updated_at"),
    }


@router.get("/runtime-settings", tags=["settings"])
async def list_runtime_settings(_: None = Depends(verify_key)):
    import db.client as db
    runtime = get_runtime()
    # Override rows carry updated_by/updated_at — fetch once and merge.
    overlays: dict[str, dict] = {}
    try:
        supabase = db.get_db()
        res = supabase.table("runtime_settings").select(
            "key, updated_by, updated_at"
        ).execute()
        for row in res.data or []:
            overlays[row.get("key")] = row
    except Exception as e:
        logger.warning(f"[runtime-settings] list overlays failed: {e}")

    return [_meta(d, runtime, overlays.get(d.key)) for d in SETTING_DEFS.values()]


@router.get("/runtime-settings/{key}", tags=["settings"])
async def get_runtime_setting(key: str, _: None = Depends(verify_key)):
    d = SETTING_DEFS.get(key)
    if d is None:
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")
    return _meta(d, get_runtime(), None)


@router.put("/runtime-settings/{key}", tags=["settings"])
async def update_runtime_setting(key: str, body: SetBody, _: None = Depends(verify_key)):
    if key not in SETTING_DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")
    err = await get_runtime().set(key, body.value, by="ui", reason=body.reason)
    if err:
        raise HTTPException(status_code=422, detail=f"{key}: {err}")
    return _meta(SETTING_DEFS[key], get_runtime(), {"updated_by": "ui"})


@router.delete("/runtime-settings/{key}", tags=["settings"])
async def reset_runtime_setting(key: str, _: None = Depends(verify_key)):
    if key not in SETTING_DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")
    err = await get_runtime().reset(key, by="ui")
    if err:
        raise HTTPException(status_code=422, detail=f"{key}: {err}")
    return {"key": key, "status": "reset to default"}


@router.get("/runtime-settings/{key}/history", tags=["settings"])
async def runtime_setting_history(
    key: str,
    limit: int = Query(50, le=200),
    _: None = Depends(verify_key),
):
    if key not in SETTING_DEFS:
        raise HTTPException(status_code=404, detail=f"Unknown setting '{key}'")
    return get_runtime().history(key, limit=limit)


@router.get("/tools", tags=["settings"])
async def list_tools(_: None = Depends(verify_key)):
    """Registered tools with risk class and enabled flag — feeds the Tools tab."""
    from tools.registry import get_registry
    from runtime_settings import get_runtime as rt

    disabled = rt().get("tools.disabled") or []
    out = []
    for tool in get_registry().list_tools():
        out.append({
            "name": tool.name,
            "description": tool.description,
            "is_mutating": getattr(tool, "is_mutating", False),
            "risk": getattr(tool, "risk", "unclassified"),
            "enabled": tool.name not in disabled,
        })
    out.sort(key=lambda t: (t["risk"], t["name"]))
    return out
