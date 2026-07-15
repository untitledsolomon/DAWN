"""
CRM Agent Router — connects DAWN to the Regent Growth Engine CRM.

This router acts as a middleware layer between DAWN's Slack bot and the
CRM's Supabase Edge Functions. It provides:

1. Lead queries (list, search, detail)
2. Pipeline analytics (funnel summary)
3. Campaign management (list, create, send)
4. Team & project management (roster, workload)

Architecture:
  Slack /leads → DAWN Slack Bot → POST /crm/leads → CRM Edge Function → Supabase
  Slack /team  → DAWN Slack Bot → POST /crm/team  → DAWN's own Supabase tables

Auth:
  Uses CRM_AGENT_API_KEY (x-agent-api-key header) for CRM Edge Functions.
  Uses DAWN's own SUPABASE_SERVICE_KEY for team/project tables.
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["crm-agent"])

# ── Config ──────────────────────────────────────────────────────────────

CRM_SUPABASE_URL = os.environ.get("CRM_SUPABASE_URL", "")
CRM_AGENT_API_KEY = os.environ.get("CRM_AGENT_API_KEY", "")
CRM_SERVICE_KEY = os.environ.get("CRM_SERVICE_KEY", "")

# The Supabase Edge Function base URL
# Format: https://<project-ref>.functions.supabase.co
CRM_FUNCTIONS_BASE = os.environ.get(
    "CRM_FUNCTIONS_BASE",
    CRM_SUPABASE_URL.replace(".supabase.co", ".functions.supabase.co")
    if CRM_SUPABASE_URL else ""
)

# DAWN's own Supabase for team/project tables
DAWN_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
DAWN_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# ── Schemas ─────────────────────────────────────────────────────────────

class LeadQueryParams(BaseModel):
    status: Optional[str] = None
    source: Optional[str] = None
    limit: int = 20
    offset: int = 0

class LeadCreate(BaseModel):
    name: str
    business: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    score: int = 0
    status: str = "new"

class LeadUpdate(BaseModel):
    status: Optional[str] = None
    score: Optional[int] = None
    name: Optional[str] = None
    business: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None

class CampaignCreate(BaseModel):
    name: str
    channel: str = "email"  # whatsapp, email, both
    subject: Optional[str] = None
    message_html: Optional[str] = None
    message_text: Optional[str] = None
    lead_ids: Optional[list[str]] = None

class TeamMemberCreate(BaseModel):
    name: str
    role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    slack_id: Optional[str] = None

class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: str = "active"  # active, paused, completed
    due_date: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[str] = None

# ── Helpers ─────────────────────────────────────────────────────────────

def _crm_headers() -> dict:
    """Headers for CRM Edge Function calls."""
    headers = {"Content-Type": "application/json"}
    if CRM_AGENT_API_KEY:
        headers["x-agent-api-key"] = CRM_AGENT_API_KEY
    elif CRM_SERVICE_KEY:
        headers["Authorization"] = f"Bearer {CRM_SERVICE_KEY}"
    return headers

def _dawn_supabase_headers() -> dict:
    """Headers for DAWN's own Supabase REST API."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DAWN_SUPABASE_KEY}",
        "apikey": DAWN_SUPABASE_KEY,
    }

async def _crm_get(path: str, params: Optional[dict] = None) -> dict:
    """GET request to a CRM Edge Function."""
    url = f"{CRM_FUNCTIONS_BASE}/functions/v1/{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=_crm_headers(), params=params)
        if resp.status_code >= 400:
            logger.error(f"CRM GET {path} failed: {resp.status_code} {resp.text[:200]}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
        return resp.json()

async def _crm_post(path: str, data: dict) -> dict:
    """POST request to a CRM Edge Function."""
    url = f"{CRM_FUNCTIONS_BASE}/functions/v1/{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=data, headers=_crm_headers())
        if resp.status_code >= 400:
            logger.error(f"CRM POST {path} failed: {resp.status_code} {resp.text[:200]}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
        return resp.json()

async def _crm_patch(path: str, data: dict) -> dict:
    """PATCH request to a CRM Edge Function."""
    url = f"{CRM_FUNCTIONS_BASE}/functions/v1/{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.patch(url, json=data, headers=_crm_headers())
        if resp.status_code >= 400:
            logger.error(f"CRM PATCH {path} failed: {resp.status_code} {resp.text[:200]}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])
        return resp.json()

async def _dawn_supabase_query(
    table: str,
    method: str = "GET",
    data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """Query DAWN's own Supabase REST API for team/project tables."""
    url = f"{DAWN_SUPABASE_URL}/rest/v1/{table}"
    headers = _dawn_supabase_headers()
    if params:
        # Convert params to Supabase query string format
        query_parts = []
        for k, v in params.items():
            if v is not None:
                query_parts.append(f"{k}=eq.{v}")
        if query_parts:
            url += "?" + "&".join(query_parts)

    async with httpx.AsyncClient(timeout=15.0) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            resp = await client.post(url, json=data, headers=headers)
        elif method == "PATCH":
            resp = await client.patch(url, json=data, headers=headers)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")

        if resp.status_code >= 400:
            logger.error(f"Supabase {method} {table} failed: {resp.status_code} {resp.text[:200]}")
            raise HTTPException(status_code=resp.status_code, detail=resp.text[:500])

        if method == "DELETE":
            return {"deleted": True}
        return resp.json()

# ── Lead Endpoints ──────────────────────────────────────────────────────

@router.get("/leads/summary")
async def get_pipeline_summary():
    """Get pipeline health metrics from CRM analytics."""
    try:
        data = await _crm_get("analytics/summary")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get pipeline summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads")
async def list_leads(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(20, le=200),
    offset: int = Query(0),
):
    """List leads from CRM with optional filters."""
    params = {}
    if status:
        params["status"] = status
    if source:
        params["source"] = source
    params["limit"] = str(limit)
    params["offset"] = str(offset)

    try:
        data = await _crm_get("leads", params=params)
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    """Get a single lead by ID."""
    try:
        data = await _crm_get(f"leads?id={lead_id}")
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads")
async def create_lead(lead: LeadCreate):
    """Create a new lead in CRM."""
    try:
        data = await _crm_post("leads", lead.model_dump(exclude_none=True))
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: str, update: LeadUpdate):
    """Update a lead's status, score, or fields."""
    try:
        data = await _crm_patch(f"leads/{lead_id}", update.model_dump(exclude_none=True))
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/import")
async def import_leads(leads: list[LeadCreate]):
    """Bulk-import leads into CRM."""
    try:
        data = await _crm_post("leads/import", {"leads": [l.model_dump(exclude_none=True) for l in leads]})
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Campaign Endpoints ──────────────────────────────────────────────────

@router.post("/campaigns")
async def create_campaign(campaign: CampaignCreate):
    """Create a new campaign in CRM."""
    try:
        data = await _crm_post("campaigns", campaign.model_dump(exclude_none=True))
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: str):
    """Execute a campaign (send emails/messages)."""
    try:
        data = await _crm_post(f"campaigns/{campaign_id}/send", {})
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Team & Project Endpoints (DAWN's own tables) ────────────────────────

@router.get("/team")
async def list_team_members():
    """List all team members."""
    try:
        data = await _dawn_supabase_query("team_members", params={"select": "*"})
        return {"members": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list team members: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/team")
async def add_team_member(member: TeamMemberCreate):
    """Add a new team member."""
    try:
        data = await _dawn_supabase_query(
            "team_members", method="POST",
            data=member.model_dump(exclude_none=True)
        )
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add team member: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/projects")
async def list_projects(status: Optional[str] = Query(None)):
    """List all projects, optionally filtered by status."""
    params = {"select": "*"}
    if status:
        params["status"] = status
    try:
        data = await _dawn_supabase_query("projects", params=params)
        return {"projects": data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/projects")
async def create_project(project: ProjectCreate):
    """Create a new project."""
    try:
        data = await _dawn_supabase_query(
            "projects", method="POST",
            data=project.model_dump(exclude_none=True)
        )
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/projects/{project_id}")
async def update_project(project_id: str, update: ProjectUpdate):
    """Update a project's status, assignee, etc."""
    try:
        data = await _dawn_supabase_query(
            f"projects?id=eq.{project_id}", method="PATCH",
            data=update.model_dump(exclude_none=True)
        )
        return data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ── Team Dashboard Endpoint ─────────────────────────────────────────────

@router.get("/dashboard")
async def get_team_dashboard():
    """
    Get a consolidated team dashboard with:
    - Pipeline summary
    - Active projects
    - Team members
    - Recent leads
    """
    results = {}

    try:
        results["pipeline"] = await _crm_get("analytics/summary")
    except Exception as e:
        logger.warning(f"Failed to fetch pipeline: {e}")
        results["pipeline"] = {"error": str(e)}

    try:
        projects_data = await _dawn_supabase_query(
            "projects", params={"select": "*,assignee:team_members(name)", "status": "eq.active"}
        )
        results["active_projects"] = projects_data if isinstance(projects_data, list) else []
    except Exception as e:
        logger.warning(f"Failed to fetch projects: {e}")
        results["active_projects"] = []

    try:
        members_data = await _dawn_supabase_query("team_members", params={"select": "*"})
        results["team_members"] = members_data if isinstance(members_data, list) else []
    except Exception as e:
        logger.warning(f"Failed to fetch team: {e}")
        results["team_members"] = []

    try:
        recent = await _crm_get("leads", params={"limit": "5"})
        results["recent_leads"] = recent.get("leads", []) if isinstance(recent, dict) else []
    except Exception as e:
        logger.warning(f"Failed to fetch recent leads: {e}")
        results["recent_leads"] = []

    return results
