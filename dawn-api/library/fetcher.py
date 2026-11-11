"""SafeFetcher — SSRF-safe, size-capped, streaming fetch with ETag support."""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

import httpx

from tools.webfetch import _resolve_safe_host
from runtime_settings import get_runtime

logger = logging.getLogger(__name__)

USER_AGENT = "DAWN-Library-Agent/1.0"


def _max_download_mb() -> int:
    try:
        return int(get_runtime().get("ingest.max_download_mb") or 200)
    except Exception:
        return 200


class FetchError(Exception):
    def __init__(self, message: str, error_class: str = "fetch.blocked"):
        super().__init__(message)
        self.error_class = error_class


async def fetch(url: str, timeout: float = 30.0, max_mb: Optional[int] = None) -> dict:
    """Fetch a URL safely. Validates the initial and final hosts against SSRF,
    streams with a size cap, and returns {bytes, content_type, final_url,
    content_hash, headers}."""
    max_mb = max_mb or _max_download_mb()
    cap = max_mb * 1024 * 1024

    safe, reason, _ip, _host = _resolve_safe_host(url)
    if not safe:
        raise FetchError(f"Refused {url}: {reason}")

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                 headers={"User-Agent": USER_AGENT}) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            chunks = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > cap:
                    raise FetchError(f"Download exceeded {max_mb} MB cap", "fetch.too_large")
                chunks.append(chunk)
            body = b"".join(chunks)
            final_url = str(resp.url)

    # Re-validate the final URL (redirects may have moved to a private host).
    safe2, reason2, _ip2, _host2 = _resolve_safe_host(final_url)
    if not safe2:
        raise FetchError(f"Refused final URL {final_url}: {reason2}")
    if len(body) == 0:
        raise FetchError("Empty body", "fetch.empty")

    return {
        "bytes": body,
        "content_type": resp.headers.get("content-type", ""),
        "final_url": final_url,
        "content_hash": hashlib.sha256(body).hexdigest(),
        "etag": resp.headers.get("etag"),
        "last_modified": resp.headers.get("last-modified"),
        "status_code": resp.status_code,
    }
