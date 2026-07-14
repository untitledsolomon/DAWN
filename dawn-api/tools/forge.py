"""
Forge CMS Integration Tool — content management operations.

Connects to the Forge CMS API for website content management.
Configure via FORGE_API_URL and FORGE_API_KEY environment variables.

Operations:
  - Pages: list, get, create, update, delete
  - Blog: list posts, create, update, publish
  - Analytics: page views, engagement, top content
"""

import os
import json
import logging
from enum import Enum
from typing import Optional
import httpx
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

FORGE_API_URL = os.environ.get("FORGE_API_URL", "")
FORGE_API_KEY = os.environ.get("FORGE_API_KEY", "")


class ForgePageOperation(str, Enum):
    LIST = "list_pages"
    GET = "get_page"
    CREATE = "create_page"
    UPDATE = "update_page"
    DELETE = "delete_page"


class ForgeBlogOperation(str, Enum):
    LIST = "list_posts"
    GET = "get_post"
    CREATE = "create_post"
    UPDATE = "update_post"
    PUBLISH = "publish_post"


class ForgeAnalyticsOperation(str, Enum):
    PAGE_VIEWS = "page_views"
    TOP_CONTENT = "top_content"
    ENGAGEMENT = "engagement"
    SUMMARY = "analytics_summary"


async def _forge_api_call(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """Make an API call to the Forge CMS backend."""
    if not FORGE_API_URL:
        return {"error": "FORGE_API_URL not configured. Set FORGE_API_URL and FORGE_API_KEY in environment."}
    
    url = f"{FORGE_API_URL.rstrip('/')}/api/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {FORGE_API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=data or {})
            elif method == "PUT":
                resp = await client.put(url, headers=headers, json=data or {})
            elif method == "DELETE":
                resp = await client.delete(url, headers=headers)
            else:
                return {"error": f"Unsupported method: {method}"}
            
            if resp.status_code in (200, 201):
                return resp.json()
            elif resp.status_code == 401:
                return {"error": "Forge API authentication failed. Check FORGE_API_KEY."}
            elif resp.status_code == 404:
                return {"error": f"Forge endpoint not found: {endpoint}"}
            else:
                return {"error": f"Forge API returned {resp.status_code}: {resp.text[:200]}"}
    except httpx.RequestError as e:
        return {"error": f"Cannot reach Forge API at {FORGE_API_URL}: {e}"}
    except Exception as e:
        return {"error": f"Forge API call failed: {e}"}


class ForgePagesTool(BaseTool):
    """Forge CMS page management operations."""

    name = "forge_pages"
    description = (
        "Forge CMS page management. List, get, create, update, and delete "
        "website pages. Use for any website content management tasks."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Page operation to perform",
                "enum": [op.value for op in ForgePageOperation],
            },
            "page_id": {
                "type": "string",
                "description": "Page ID or slug for individual operations. Optional.",
            },
            "title": {
                "type": "string",
                "description": "Page title (for create/update). Optional.",
            },
            "content": {
                "type": "string",
                "description": "Page content (markdown or HTML, for create/update). Optional.",
            },
            "status": {
                "type": "string",
                "description": "Page status: draft, published, archived. Optional.",
                "enum": ["draft", "published", "archived"],
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        page_id = kwargs.get("page_id")
        title = kwargs.get("title")
        content = kwargs.get("content")
        status = kwargs.get("status")

        if not FORGE_API_URL:
            return ToolResult(
                success=False,
                error="Forge CMS not configured. Set FORGE_API_URL and FORGE_API_KEY environment variables.",
            )

        try:
            if operation == ForgePageOperation.LIST.value:
                params = f"?status={status}" if status else ""
                result = await _forge_api_call(f"pages{params}")
            elif operation == ForgePageOperation.GET.value:
                if not page_id:
                    return ToolResult(success=False, error="page_id is required for get_page")
                result = await _forge_api_call(f"pages/{page_id}")
            elif operation == ForgePageOperation.CREATE.value:
                if not title:
                    return ToolResult(success=False, error="title is required for create_page")
                data = {"title": title, "content": content or "", "status": status or "draft"}
                result = await _forge_api_call("pages", method="POST", data=data)
            elif operation == ForgePageOperation.UPDATE.value:
                if not page_id:
                    return ToolResult(success=False, error="page_id is required for update_page")
                data = {}
                if title:
                    data["title"] = title
                if content:
                    data["content"] = content
                if status:
                    data["status"] = status
                result = await _forge_api_call(f"pages/{page_id}", method="PUT", data=data)
            elif operation == ForgePageOperation.DELETE.value:
                if not page_id:
                    return ToolResult(success=False, error="page_id is required for delete_page")
                result = await _forge_api_call(f"pages/{page_id}", method="DELETE")
            else:
                return ToolResult(success=False, error=f"Unknown page operation: {operation}")

            if isinstance(result, dict) and "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Forge pages error: {e}")
            return ToolResult(success=False, error=str(e))


class ForgeBlogTool(BaseTool):
    """Forge CMS blog management operations."""

    name = "forge_blog"
    description = (
        "Forge CMS blog management. List, get, create, update, and publish "
        "blog posts. Use for any blog or article content tasks."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Blog operation to perform",
                "enum": [op.value for op in ForgeBlogOperation],
            },
            "post_id": {
                "type": "string",
                "description": "Post ID or slug for individual operations. Optional.",
            },
            "title": {
                "type": "string",
                "description": "Post title (for create/update). Optional.",
            },
            "content": {
                "type": "string",
                "description": "Post content (markdown, for create/update). Optional.",
            },
            "tags": {
                "type": "string",
                "description": "Comma-separated tags. Optional.",
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        post_id = kwargs.get("post_id")
        title = kwargs.get("title")
        content = kwargs.get("content")
        tags = kwargs.get("tags")

        if not FORGE_API_URL:
            return ToolResult(
                success=False,
                error="Forge CMS not configured. Set FORGE_API_URL and FORGE_API_KEY environment variables.",
            )

        try:
            if operation == ForgeBlogOperation.LIST.value:
                result = await _forge_api_call("blog/posts")
            elif operation == ForgeBlogOperation.GET.value:
                if not post_id:
                    return ToolResult(success=False, error="post_id is required for get_post")
                result = await _forge_api_call(f"blog/posts/{post_id}")
            elif operation == ForgeBlogOperation.CREATE.value:
                if not title:
                    return ToolResult(success=False, error="title is required for create_post")
                data = {"title": title, "content": content or ""}
                if tags:
                    data["tags"] = [t.strip() for t in tags.split(",")]
                result = await _forge_api_call("blog/posts", method="POST", data=data)
            elif operation == ForgeBlogOperation.UPDATE.value:
                if not post_id:
                    return ToolResult(success=False, error="post_id is required for update_post")
                data = {}
                if title:
                    data["title"] = title
                if content:
                    data["content"] = content
                if tags:
                    data["tags"] = [t.strip() for t in tags.split(",")]
                result = await _forge_api_call(f"blog/posts/{post_id}", method="PUT", data=data)
            elif operation == ForgeBlogOperation.PUBLISH.value:
                if not post_id:
                    return ToolResult(success=False, error="post_id is required for publish_post")
                result = await _forge_api_call(f"blog/posts/{post_id}/publish", method="POST")
            else:
                return ToolResult(success=False, error=f"Unknown blog operation: {operation}")

            if isinstance(result, dict) and "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Forge blog error: {e}")
            return ToolResult(success=False, error=str(e))


class ForgeAnalyticsTool(BaseTool):
    """Forge CMS analytics operations."""

    name = "forge_analytics"
    description = (
        "Forge CMS analytics. Get page views, top content, engagement metrics, "
        "and analytics summaries. Use for any website performance questions."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Analytics operation to perform",
                "enum": [op.value for op in ForgeAnalyticsOperation],
            },
            "period": {
                "type": "string",
                "description": "Time period: '7d', '30d', '90d', 'this_month', 'last_month'. Optional.",
            },
            "limit": {
                "type": "integer",
                "description": "Max results to return. Optional, default 10.",
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        period = kwargs.get("period", "30d")
        limit = kwargs.get("limit", 10)

        if not FORGE_API_URL:
            return ToolResult(
                success=False,
                error="Forge CMS not configured. Set FORGE_API_URL and FORGE_API_KEY environment variables.",
            )

        try:
            params = f"?period={period}&limit={limit}"

            if operation == ForgeAnalyticsOperation.PAGE_VIEWS.value:
                result = await _forge_api_call(f"analytics/page-views{params}")
            elif operation == ForgeAnalyticsOperation.TOP_CONTENT.value:
                result = await _forge_api_call(f"analytics/top-content{params}")
            elif operation == ForgeAnalyticsOperation.ENGAGEMENT.value:
                result = await _forge_api_call(f"analytics/engagement{params}")
            elif operation == ForgeAnalyticsOperation.SUMMARY.value:
                result = await _forge_api_call(f"analytics/summary{params}")
            else:
                return ToolResult(success=False, error=f"Unknown analytics operation: {operation}")

            if isinstance(result, dict) and "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Forge analytics error: {e}")
            return ToolResult(success=False, error=str(e))
