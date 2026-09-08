"""
MCP OAuth 2.1 (MCP Authorization spec) support for HTTP MCP servers.

DAWN previously only supported static bearer tokens typed into a form field.
Servers implementing the MCP Authorization spec (RFC 9728 + RFC 8414 +
OAuth 2.1 + PKCE + DCR) respond to unauthenticated calls with a 401 +
`WWW-Authenticate` challenge and require a browser sign-in/consent flow. This
module:

  1. Auto-detects which auth mode a server needs (probe -> 401 challenge?).
  2. Runs discovery (Protected Resource Metadata -> Authorization Server
     Metadata) + Dynamic Client Registration (DCR).
  3. Builds the authorization URL (PKCE S256) for the browser to open.
  4. Exchanges the callback code at the token endpoint and persists tokens.
  5. Refreshes expired tokens transparently.

Tokens are stored per-server in the `mcp_oauth_tokens` table (one row per
server, matching DAWN's one-connection-per-server model).

We reuse the installed MCP SDK's building blocks (`mcp.client.auth.utils`) for
the protocol-heavy parts (discovery URL construction, registration request
building, response parsing) rather than hand-rolling the wire formats, but we
drive the flow ourselves across two HTTP routes because DAWN's model needs the
browser to open the authorization URL in a popup and hit a separate callback.
"""
import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

from config import settings

logger = logging.getLogger(__name__)

try:
    import httpx2
    from mcp.client.auth.utils import (
        build_oauth_authorization_server_metadata_discovery_urls,
        build_protected_resource_metadata_discovery_urls,
        create_client_registration_request,
        create_oauth_metadata_request,
        extract_resource_metadata_from_www_auth,
        handle_auth_metadata_response,
        handle_protected_resource_response,
        handle_registration_response,
    )
    from mcp.client.auth.oauth2 import PKCEParameters
    from mcp.shared.auth import OAuthToken
    from mcp.shared.inbound import MCP_PROTOCOL_VERSION_HEADER
    HAS_OAUTH = True
except ImportError:
    HAS_OAUTH = False
    httpx2 = None  # type: ignore


def oauth_enabled() -> bool:
    """Whether the MCP OAuth machinery is importable (mcp SDK present)."""
    return HAS_OAUTH


# ── In-memory pending flows ────────────────────────────────────────────────
# The authorization code flow is split across two routes: /oauth/start returns
# the authorization URL, /oauth/callback receives the code. The code_verifier
# and state must survive between the two. DAWN runs a single uvicorn worker, so
# an in-memory dict keyed by `state` is sufficient; a restart between the two
# requests simply forces the user to retry the sign-in.

@dataclass
class PendingFlow:
    server_url: str
    state: str
    code_verifier: str
    client_id: str
    client_secret: Optional[str]
    token_endpoint_auth_method: Optional[str]
    authorization_endpoint: str
    token_endpoint: str
    redirect_uri: str
    scope: Optional[str] = None


_pending_flows: dict[str, PendingFlow] = {}


def _redirect_uri() -> str:
    """The OAuth redirect URI for DAWN's callback route."""
    base = (settings.dawn_public_url or "http://localhost:8000").rstrip("/")
    return f"{base}/mcp/oauth/callback"


# ── Token persistence (Supabase-backed) ────────────────────────────────────

async def _load_token_row(server_id: str) -> Optional[dict]:
    import db.client as db
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").select(
        "*"
    ).eq("server_id", server_id).maybe_single().execute())
    # maybe_single() returns None when no row matches (0 rows), so guard against it.
    return res.data if res and res.data else None


async def _save_token_row(server_id: str, row: dict) -> None:
    import db.client as db
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").upsert(
        {**row, "server_id": server_id}, on_conflict="server_id"
    ).execute())


async def delete_tokens(server_id: str) -> None:
    """Remove stored OAuth tokens for a server (re-auth / revoke)."""
    import db.client as db
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").delete().eq("server_id", server_id).execute())


async def get_access_token(server_id: str) -> Optional[str]:
    """Return a valid access token for the server, refreshing if expired.

    Returns None if no OAuth tokens are stored (server uses static key / no auth).
    """
    row = await _load_token_row(server_id)
    if not row or not row.get("access_token"):
        return None
    expires_at = row.get("expires_at")
    if expires_at and _is_expired(expires_at):
        refreshed = await refresh_tokens(server_id)
        if refreshed:
            return refreshed
        # Refresh failed — fall through to the (possibly still-usable) token,
        # the server will 401 and the caller can surface the error.
    return row.get("access_token")


def _is_expired(expires_at) -> bool:
    """True if the token expires within the next 30s (clock-skew buffer)."""
    if not expires_at:
        return False
    try:
        import datetime
        if isinstance(expires_at, str):
            expires_at = datetime.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return (expires_at - now).total_seconds() <= 30
    except Exception:
        return False


async def refresh_tokens(server_id: str) -> Optional[str]:
    """Refresh an expired token using the stored refresh_token grant.

    Returns the new access token on success, None on failure.
    """
    row = await _load_token_row(server_id)
    if not row or not row.get("refresh_token") or not row.get("token_endpoint"):
        return None
    if not HAS_OAUTH:
        return None

    data = {
        "grant_type": "refresh_token",
        "refresh_token": row["refresh_token"],
        "client_id": row.get("client_id") or "",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    # Authenticate the token request per the registered method.
    auth_method = row.get("token_endpoint_auth_method")
    client_secret = row.get("client_secret")
    if auth_method == "client_secret_basic" and client_secret:
        import base64
        from urllib.parse import quote
        creds = f"{quote(row.get('client_id') or '', safe='')}:{quote(client_secret, safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(creds.encode()).decode()
        data.pop("client_secret", None)
    elif auth_method == "client_secret_post" and client_secret:
        data["client_secret"] = client_secret

    try:
        async with httpx2.AsyncClient() as client:
            resp = await client.post(row["token_endpoint"], data=data, headers=headers)
        if resp.status_code != 200:
            logger.warning(f"OAuth token refresh failed for {server_id}: HTTP {resp.status_code}")
            return None
        token = OAuthToken.model_validate_json(await resp.aread())
        if token.scope is None:
            token.scope = row.get("scope")
        if token.refresh_token is None:
            token.refresh_token = row.get("refresh_token")  # AS may not rotate
        await _save_token_row(server_id, _token_row_from_token(token, row))
        return token.access_token
    except Exception as e:
        logger.warning(f"OAuth token refresh failed for {server_id}: {e}")
        return None


def _token_row_from_token(token: OAuthToken, existing: dict) -> dict:
    """Build a mcp_oauth_tokens row from an OAuthToken, carrying forward client info."""
    import datetime
    expires_at = None
    if token.expires_in:
        expires_at = (datetime.datetime.now(datetime.timezone.utc)
                      + datetime.timedelta(seconds=token.expires_in)).isoformat()
    return {
        "access_token": token.access_token,
        "refresh_token": token.refresh_token or existing.get("refresh_token"),
        "expires_at": expires_at,
        "client_id": existing.get("client_id"),
        "client_secret": existing.get("client_secret"),
        "token_endpoint": existing.get("token_endpoint"),
        "token_endpoint_auth_method": existing.get("token_endpoint_auth_method"),
        "scope": token.scope or existing.get("scope"),
    }


# ── Discovery + DCR ────────────────────────────────────────────────────────

async def _send(client: httpx2.AsyncClient, request: httpx2.Request) -> httpx2.Response:
    """Send an SDK-built httpx2.Request and return the response."""
    return await client.send(request)


async def probe_oauth(server_url: str) -> Optional[str]:
    """Probe a server unauthenticated and detect whether it requires OAuth.

    Returns the discovered Authorization Server Metadata URL's authorization
    server URL (issuer) if the server challenges with a Bearer
    resource_metadata, else None (server uses static key / no auth).
    """
    if not HAS_OAUTH:
        return None
    try:
        async with httpx2.AsyncClient() as client:
            resp = await client.get(
                server_url,
                headers={MCP_PROTOCOL_VERSION_HEADER: "2025-06-18"},
            )
            if resp.status_code != 401:
                return None
            www_auth = resp.headers.get("www-authenticate", "")
            if "Bearer" not in www_auth:
                return None
            # Follow the protected-resource-metadata URL from the challenge.
            prm_url = extract_resource_metadata_from_www_auth(resp)
            prm_urls = build_protected_resource_metadata_discovery_urls(prm_url, server_url)
            for url in prm_urls:
                prm_resp = await _send(client, create_oauth_metadata_request(url))
                prm = await handle_protected_resource_response(prm_resp)
                if prm and prm.authorization_servers:
                    return str(prm.authorization_servers[0])
    except Exception as e:
        logger.warning(f"OAuth probe failed for {server_url}: {e}")
    return None


async def _discover_oauth_metadata(server_url: str, auth_server_url: str) -> Optional[dict]:
    """Fetch the Authorization Server Metadata for the discovered issuer."""
    if not HAS_OAUTH:
        return None
    async with httpx2.AsyncClient() as client:
        for url in build_oauth_authorization_server_metadata_discovery_urls(auth_server_url, server_url):
            resp = await _send(client, create_oauth_metadata_request(url))
            ok, asm = await handle_auth_metadata_response(resp)
            if ok and asm:
                return asm
    return None


async def _register_client(server_url: str, oauth_metadata: dict, redirect_uri: str) -> dict:
    """Register a dynamic client (DCR) against the AS metadata."""
    from mcp.shared.auth import OAuthClientMetadata
    client_metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="DAWN",
    )
    auth_base = _origin(server_url)
    request = create_client_registration_request(oauth_metadata, client_metadata, auth_base)
    async with httpx2.AsyncClient() as client:
        resp = await _send(client, request)
        client_info = await handle_registration_response(resp)
    return {
        "client_id": client_info.client_id,
        "client_secret": client_info.client_secret,
        "token_endpoint_auth_method": client_info.token_endpoint_auth_method,
    }


def _origin(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def start_oauth_flow(server_url: str) -> dict:
    """Run discovery + DCR and build the authorization URL for a server.

    Returns a dict with the authorization URL to open in a popup, plus the
    `state` used to correlate the callback. Raises ValueError if the server
    does not support OAuth.
    """
    if not HAS_OAUTH:
        raise ValueError("MCP OAuth support not available (mcp SDK missing)")

    auth_server_url = await probe_oauth(server_url)
    if not auth_server_url:
        raise ValueError("Server does not require OAuth (no 401 Bearer challenge)")

    oauth_metadata = await _discover_oauth_metadata(server_url, auth_server_url)
    if not oauth_metadata or not oauth_metadata.authorization_endpoint or not oauth_metadata.token_endpoint:
        raise ValueError("Server advertised no usable OAuth authorization/token endpoint")

    redirect_uri = _redirect_uri()
    client_info = await _register_client(server_url, oauth_metadata, redirect_uri)

    # Ensure the client we registered is one the code flow can act on.
    _check_registration_usable(client_info)

    pkce = PKCEParameters.generate()
    state = secrets.token_urlsafe(32)

    params = {
        "response_type": "code",
        "client_id": client_info["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
    }
    # Request the first scope the AS advertises (e.g. "mcp"), if any.
    scopes_supported = oauth_metadata.scopes_supported or []
    scope = scopes_supported[0] if scopes_supported else None
    if scope:
        params["scope"] = scope

    authorization_url = f"{oauth_metadata.authorization_endpoint}?{urlencode(params)}"

    _pending_flows[state] = PendingFlow(
        server_url=server_url,
        state=state,
        code_verifier=pkce.code_verifier,
        client_id=client_info["client_id"],
        client_secret=client_info.get("client_secret"),
        token_endpoint_auth_method=client_info.get("token_endpoint_auth_method"),
        authorization_endpoint=str(oauth_metadata.authorization_endpoint),
        token_endpoint=str(oauth_metadata.token_endpoint),
        redirect_uri=redirect_uri,
        scope=scope,
    )

    return {"authorization_url": authorization_url, "state": state}


def _check_registration_usable(client_info: dict) -> None:
    """Reject a registration we cannot act on (mirrors the SDK's check)."""
    method = client_info.get("token_endpoint_auth_method")
    if method not in (None, "none", "client_secret_basic", "client_secret_post"):
        raise ValueError(f"Server registered unsupported token_endpoint_auth_method: {method!r}")
    if method in ("client_secret_basic", "client_secret_post") and not client_info.get("client_secret"):
        raise ValueError(f"Server registered for {method!r} but issued no client_secret")


async def handle_oauth_callback(server_id: str, code: str, state: str) -> dict:
    """Exchange the authorization code at the token endpoint and persist tokens.

    Returns a summary dict. Raises ValueError on failure.
    """
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise ValueError("Unknown or expired OAuth state — please retry sign-in")
    if not HAS_OAUTH:
        raise ValueError("MCP OAuth support not available")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": flow.redirect_uri,
        "client_id": flow.client_id,
        "code_verifier": flow.code_verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if flow.token_endpoint_auth_method == "client_secret_basic" and flow.client_secret:
        import base64
        from urllib.parse import quote
        creds = f"{quote(flow.client_id, safe='')}:{quote(flow.client_secret, safe='')}"
        headers["Authorization"] = "Basic " + base64.b64encode(creds.encode()).decode()
        data.pop("client_secret", None)
    elif flow.token_endpoint_auth_method == "client_secret_post" and flow.client_secret:
        data["client_secret"] = flow.client_secret

    try:
        async with httpx2.AsyncClient() as client:
            resp = await client.post(flow.token_endpoint, data=data, headers=headers)
        if resp.status_code not in (200, 201):
            body = (await resp.aread()).decode("utf-8", "replace")
            raise ValueError(f"Token exchange failed (HTTP {resp.status_code}): {body}")
        token = OAuthToken.model_validate_json(await resp.aread())
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Token exchange failed: {e}")

    existing = {
        "client_id": flow.client_id,
        "client_secret": flow.client_secret,
        "token_endpoint": flow.token_endpoint,
        "token_endpoint_auth_method": flow.token_endpoint_auth_method,
        "scope": token.scope or flow.scope,
    }
    await _save_token_row(server_id, _token_row_from_token(token, existing))

    return {"status": "success", "server_id": server_id}
