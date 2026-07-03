"""
Web search tool — Brave Search API (https://api.search.brave.com).
Requires BRAVE_SEARCH_API_KEY in config.settings. Read-only, no sandbox
concerns — the risk surface here is cost/rate-limit, not filesystem/exec safety.
"""
import logging
import httpx
from tools.base import BaseTool, ToolResult
from config import settings

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
REQUEST_TIMEOUT_SECONDS = 10


class WebSearchTool(BaseTool):
    name = "web_search"
    description = (
        "Search the web for current information. Returns a list of results with "
        "title, URL, and a short snippet. Use this for anything that might have "
        "changed since training, or that requires looking something up externally."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query. Keep it short and specific (3-6 words works best).",
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return. Defaults to 5, max 10.",
            },
        },
        "required": ["query"],
    }

    def __init__(self):
        self.api_key = getattr(settings, "brave_search_api_key", None)
        if not self.api_key:
            logger.warning(
                "WebSearchTool initialised without BRAVE_SEARCH_API_KEY set — "
                "calls will fail until it's configured."
            )

    async def run(self, query: str, count: int = 5) -> ToolResult:
        if not self.api_key:
            return ToolResult(
                success=False,
                error="BRAVE_SEARCH_API_KEY is not configured — web search is unavailable.",
            )

        count = max(1, min(count, 10))

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                response = await client.get(
                    BRAVE_ENDPOINT,
                    params={"q": query, "count": count},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key,
                    },
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"Search timed out after {REQUEST_TIMEOUT_SECONDS}s")
        except httpx.HTTPError as e:
            return ToolResult(success=False, error=f"Search request failed: {e}")

        if response.status_code == 401:
            return ToolResult(success=False, error="Brave Search API key rejected (401) — check config")
        if response.status_code == 429:
            return ToolResult(success=False, error="Brave Search rate limit hit (429) — try again shortly")
        if response.status_code != 200:
            return ToolResult(success=False, error=f"Brave Search returned HTTP {response.status_code}")

        try:
            data = response.json()
        except ValueError:
            return ToolResult(success=False, error="Brave Search returned an unparseable response")

        results = data.get("web", {}).get("results", [])
        formatted = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            }
            for r in results[:count]
        ]

        if not formatted:
            return ToolResult(success=True, output=[], metadata={"query": query, "result_count": 0})

        return ToolResult(success=True, output=formatted, metadata={"query": query, "result_count": len(formatted)})
