"""
Regression test for the mcp_oauth import bug.

tools/mcp_oauth.py used to `import httpx2` (a typo for `httpx`, and not a
package that exists / is installed). That ImportError was swallowed by the
module's own `except ImportError: HAS_OAUTH = False` guard, so the whole
OAuth auto-detect/DCR/token-exchange flow silently no-op'd forever -- no
error was ever raised, `oauth_enabled()` just always returned False and
`probe_oauth()` always returned None, regardless of what the target MCP
server actually supported.

This test fails if that regresses: it asserts the module imports with
HAS_OAUTH == True (given `mcp` and `httpx` are installed, which they are per
requirements.txt), and that no stray `httpx2` symbol/reference survives in
the module's namespace or source.
"""
import importlib
import inspect

import tools.mcp_oauth as mcp_oauth


def test_mcp_oauth_reports_enabled():
    """oauth_enabled() must reflect real dependency availability, not a typo'd import."""
    importlib.reload(mcp_oauth)
    assert mcp_oauth.oauth_enabled() is True, (
        "HAS_OAUTH is False -- the OAuth subsystem is not loading. "
        "Check that `httpx` (not `httpx2`) is imported at the top of mcp_oauth.py."
    )


def test_no_httpx2_reference_remains():
    """Guard against the typo being reintroduced anywhere in the module."""
    source = inspect.getsource(mcp_oauth)
    assert "httpx2" not in source, "Found a stray `httpx2` reference in mcp_oauth.py"


def test_probe_oauth_uses_real_httpx_client(monkeypatch):
    """probe_oauth should actually attempt a network call via httpx, not short-circuit to None."""
    import asyncio

    called = {}

    class DummyResponse:
        status_code = 200

        def json(self):
            return {}

        @property
        def headers(self):
            return {}

    class DummyAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, **kwargs):
            called["url"] = url
            return DummyResponse()

    monkeypatch.setattr(mcp_oauth.httpx, "AsyncClient", DummyAsyncClient)

    asyncio.run(mcp_oauth.probe_oauth("https://example.invalid/mcp"))
    assert called.get("url") == "https://example.invalid/mcp", (
        "probe_oauth never reached httpx.AsyncClient.post -- HAS_OAUTH is "
        "probably still False, meaning the import guard is broken again."
    )
