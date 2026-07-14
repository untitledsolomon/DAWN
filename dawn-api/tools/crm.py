"""
CRM Tool — connects to the Regent Growth Engine (Supabase Edge Functions).

Endpoints (from regent-growth-engine):
  GET  /analytics/summary   — pipeline health (lead counts, campaign stats, conversion rate)
  GET  /leads               — query leads (filter: status, source, limit, offset)
  POST /leads               — create a single lead
  PATCH /leads/:id          — update lead status/score/fields
  POST /leads/import        — bulk-import leads

Auth: x-agent-api-key header (set via CRM_AGENT_API_KEY env var)
"""

import os
import json
import logging
from enum import Enum
from typing import Optional
import httpx
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

CRM_FUNCTIONS_BASE = os.environ.get("CRM_FUNCTIONS_BASE", "")
CRM_AGENT_API_KEY = os.environ.get("CRM_AGENT_API_KEY", "")


class CRMAnalyticsOperation(str, Enum):
    SUMMARY = "summary"


class CRMLeadOperation(str, Enum):
    LIST = "list"
    GET = "get"
    CREATE = "create"
    UPDATE = "update"
    IMPORT = "import"


async def _crm_api_call(
    endpoint: str,
    method: str = "GET",
    data: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """Make an API call to the Growth Engine Supabase Edge Function."""
    if not CRM_FUNCTIONS_BASE:
        return {"error": "CRM_FUNCTIONS_BASE not configured. Set CRM_FUNCTIONS_BASE and CRM_AGENT_API_KEY in environment."}

    url = f"{CRM_FUNCTIONS_BASE.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "x-agent-api-key": CRM_AGENT_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers, params=params)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=data or {})
            elif method == "PATCH":
                resp = await client.patch(url, headers=headers, json=data or {})
            else:
                return {"error": f"Unsupported method: {method}"}

            if resp.status_code == 200 or resp.status_code == 201:
                return resp.json()
            elif resp.status_code == 401:
                return {"error": "CRM API authentication failed. Check CRM_AGENT_API_KEY."}
            elif resp.status_code == 403:
                return {"error": "CRM API access denied. Check agent scopes."}
            elif resp.status_code == 404:
                return {"error": f"CRM endpoint not found: {endpoint}"}
            else:
                return {"error": f"CRM API returned {resp.status_code}: {resp.text[:300]}"}
    except httpx.RequestError as e:
        return {"error": f"Cannot reach CRM API at {CRM_FUNCTIONS_BASE}: {e}"}
    except Exception as e:
        return {"error": f"CRM API call failed: {e}"}


class CRMAnalyticsTool(BaseTool):
    """CRM analytics — pipeline health summary."""

    name = "crm_analytics"
    description = (
        "CRM analytics — get pipeline health summary including lead counts by status, "
        "campaign stats, conversion rates, and reply rates. "
        "Calls the Regent Growth Engine analytics endpoint."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Analytics operation",
                "enum": [op.value for op in CRMAnalyticsOperation],
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")

        if not CRM_FUNCTIONS_BASE:
            return ToolResult(
                success=False,
                error="CRM not configured. Set CRM_FUNCTIONS_BASE and CRM_AGENT_API_KEY environment variables.",
            )

        try:
            if operation == CRMAnalyticsOperation.SUMMARY.value:
                result = await _crm_api_call("analytics/summary")
            else:
                return ToolResult(success=False, error=f"Unknown analytics operation: {operation}")

            if isinstance(result, dict) and "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"CRM analytics error: {e}")
            return ToolResult(success=False, error=str(e))


class CRMLeadTool(BaseTool):
    """CRM lead operations — query, create, update, import leads."""

    name = "crm_leads"
    description = (
        "CRM lead operations. Query leads (filter by status, source), "
        "create a single lead, update lead status/score, or bulk-import leads. "
        "Calls the Regent Growth Engine leads endpoint."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Lead operation to perform",
                "enum": [op.value for op in CRMLeadOperation],
            },
            "status": {
                "type": "string",
                "description": "Filter by status (for 'list'): new, contacted, follow-up, interested, closed. Optional.",
            },
            "source": {
                "type": "string",
                "description": "Filter by source (for 'list'): phantombuster, linkedin, referral, website, cold-outreach. Optional.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return (for 'list'). Default 50, max 200. Optional.",
            },
            "lead_id": {
                "type": "string",
                "description": "Lead UUID (for 'update'). Required for update operation.",
            },
            "lead_data": {
                "type": "object",
                "description": (
                    "Lead data (for 'create' or 'update'). "
                    "Fields: name, business, email, phone, source, status, score, tags, linkedinUrl. "
                    "For 'import', pass an array of lead objects."
                ),
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")

        if not CRM_FUNCTIONS_BASE:
            return ToolResult(
                success=False,
                error="CRM not configured. Set CRM_FUNCTIONS_BASE and CRM_AGENT_API_KEY environment variables.",
            )

        try:
            if operation == CRMLeadOperation.LIST.value:
                params = {}
                if kwargs.get("status"):
                    params["status"] = kwargs["status"]
                if kwargs.get("source"):
                    params["source"] = kwargs["source"]
                if kwargs.get("limit"):
                    params["limit"] = str(min(kwargs["limit"], 200))
                result = await _crm_api_call("leads", method="GET", params=params)

            elif operation == CRMLeadOperation.CREATE.value:
                lead_data = kwargs.get("lead_data")
                if not lead_data:
                    return ToolResult(success=False, error="lead_data is required for create")
                result = await _crm_api_call("leads", method="POST", data=lead_data)

            elif operation == CRMLeadOperation.UPDATE.value:
                lead_id = kwargs.get("lead_id")
                if not lead_id:
                    return ToolResult(success=False, error="lead_id is required for update")
                lead_data = kwargs.get("lead_data")
                if not lead_data:
                    return ToolResult(success=False, error="lead_data is required for update")
                result = await _crm_api_call(f"leads/{lead_id}", method="PATCH", data=lead_data)

            elif operation == CRMLeadOperation.IMPORT.value:
                lead_data = kwargs.get("lead_data")
                if not lead_data:
                    return ToolResult(success=False, error="lead_data (array of leads) is required for import")
                result = await _crm_api_call("leads/import", method="POST", data=lead_data)

            else:
                return ToolResult(success=False, error=f"Unknown lead operation: {operation}")

            if isinstance(result, dict) and "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"CRM leads error: {e}")
            return ToolResult(success=False, error=str(e))
