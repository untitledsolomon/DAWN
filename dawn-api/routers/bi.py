"""
Business Intelligence endpoints — dashboards, reports, data sources.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


class DashboardCreate(BaseModel):
    title: str
    description: Optional[str] = None
    layout: Optional[dict] = None
    widgets: Optional[list] = None
    data_sources: Optional[list] = None


class DataSourceCreate(BaseModel):
    name: str
    source_type: str  # 'postgresql', 'mysql', 'bigquery', 'csv', 'excel', 'google_sheets', 'api'
    connection_config: dict


@router.get("/bi/dashboards", tags=["bi"])
async def list_dashboards(_: None = Depends(verify_key)):
    """List all BI dashboards."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_dashboards").select("*").order("title").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list dashboards: {e}")
        return []


@router.post("/bi/dashboards", tags=["bi"])
async def create_dashboard(req: DashboardCreate, _: None = Depends(verify_key)):
    """Create a new dashboard."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_dashboards").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create dashboard")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bi/dashboards/{dashboard_id}", tags=["bi"])
async def get_dashboard(dashboard_id: str, _: None = Depends(verify_key)):
    """Get a single dashboard."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_dashboards").select("*").eq("id", dashboard_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        return res.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bi/dashboards/{dashboard_id}", tags=["bi"])
async def delete_dashboard(dashboard_id: str, _: None = Depends(verify_key)):
    """Delete a dashboard."""
    try:
        supabase = db.get_db()
        supabase.table("bi_dashboards").delete().eq("id", dashboard_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bi/data-sources", tags=["bi"])
async def list_data_sources(_: None = Depends(verify_key)):
    """List all data sources."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_data_sources").select("*").order("name").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list data sources: {e}")
        return []


@router.post("/bi/data-sources", tags=["bi"])
async def create_data_source(req: DataSourceCreate, _: None = Depends(verify_key)):
    """Add a new data source."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_data_sources").insert(req.model_dump()).execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to create data source")
        return res.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/bi/data-sources/{source_id}", tags=["bi"])
async def delete_data_source(source_id: str, _: None = Depends(verify_key)):
    """Delete a data source."""
    try:
        supabase = db.get_db()
        supabase.table("bi_data_sources").delete().eq("id", source_id).execute()
        return {"status": "deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bi/reports", tags=["bi"])
async def list_reports(_: None = Depends(verify_key)):
    """List all scheduled reports."""
    try:
        supabase = db.get_db()
        res = supabase.table("bi_reports").select("*, bi_dashboards(title)").order("title").execute()
        return res.data or []
    except Exception as e:
        logger.error(f"Failed to list reports: {e}")
        return []
