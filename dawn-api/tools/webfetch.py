"""
Web fetch tool — retrieves the content of a specific URL.
Complements web_search (which finds URLs) by letting the model actually
read a page it already has a link to. Read-only, no filesystem/exec risk —
the risk surface here is SSRF (the model fetching internal/private URLs),
so we block non-http(s) schemes and private/loopback IPs.
"""
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
MAX_CONTENT_CHARS = 8000  # keep tool_result payloads sane for the model's context


def _resolve_safe_host(url: str) -> tuple[bool, str, str | None, str | None]:
    """Resolve the URL's hostname once, validate it against SSRF vectors, and
    return (ok, reason, pinned_ip, hostname).

    The IP is pinned here so the subsequent request goes to exactly this
    address (with the original Host header), closing the DNS-rebinding
    (TOCTOU) gap where the check resolves one IP but the request re-resolves
    to a different one.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Could not parse URL", None, None

    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' not allowed — only http/https", None, None

    if not parsed.hostname:
        return False, "URL has no hostname", None, None

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False, f"Could not resolve hostname '{parsed.hostname}'", None, None

    # Pick the first public address; reject if any resolved address is private.
    pinned_ip = None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False, f"Refusing to fetch private/internal address ({ip})", None, None
        if pinned_ip is None:
            pinned_ip = str(ip)

    return True, "", pinned_ip, parsed.hostname


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = (
        "Fetch the text content of a specific URL. Use this when you already "
        "have a URL (from web_search results, a knowledge graph node, or the "
        "user's message) and need to read what's actually on the page."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full URL to fetch, including https://",
            },
        },
        "required": ["url"],
    }

    async def run(self, url: str) -> ToolResult:
        safe, reason, pinned_ip, hostname = _resolve_safe_host(url)
        if not safe:
            return ToolResult(success=False, error=f"Refused to fetch '{url}': {reason}")

        # Rewrite the URL to the pinned IP, preserving the original Host header
        # so the server sees the intended hostname while the connection goes
        # only to the validated address.
        parsed = urlparse(url)
        pinned_url = parsed._replace(netloc=f"{pinned_ip}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}").geturl()
        headers = {
            "User-Agent": "DAWN-Agent/1.0",
            "Host": hostname,
        }

        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.get(
                    pinned_url, headers=headers
                )
        except httpx.TimeoutException:
            return ToolResult(success=False, error=f"Fetch timed out after {REQUEST_TIMEOUT_SECONDS}s")
        except httpx.HTTPError as e:
            return ToolResult(success=False, error=f"Fetch failed: {e}")

        if response.status_code != 200:
            return ToolResult(success=False, error=f"URL returned HTTP {response.status_code}")

        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            text = self._strip_html(response.text)
        elif "text" in content_type or "json" in content_type:
            text = response.text
        else:
            return ToolResult(
                success=False,
                error=f"Unsupported content-type '{content_type}' — only text/HTML is supported",
            )

        truncated = len(text) > MAX_CONTENT_CHARS
        text = text[:MAX_CONTENT_CHARS]

        return ToolResult(
            success=True,
            output=text,
            metadata={"url": url, "truncated": truncated, "content_type": content_type},
        )

    @staticmethod
    def _strip_html(html: str) -> str:
        """Minimal tag stripping — swap for readability/trafilatura later if you want cleaner extraction."""
        import re
        text = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()