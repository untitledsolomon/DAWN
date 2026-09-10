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
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

from config import settings

logger = logging.getLogger(__name__)

# ── Token encryption at rest ─────────────────────────────────────────────────
# OAuth tokens (access_token, refresh_token, client_secret) are sensitive
# credentials. Encrypt them with Fernet before writing to the DB so a leaked
# row isn't directly usable. The key comes from DAWN_TOKEN_ENCRYPTION_KEY.
_TOKEN_FIELDS = ("access_token", "refresh_token", "client_secret")

_fernet = None
_fernet_warned = False


def _get_fernet():
    """Return a lazily-initialized Fernet cipher, or None if no key is set."""
    global _fernet, _fernet_warned
    if _fernet is not None:
        return _fernet
    key = getattr(settings, "dawn_token_encryption_key", None)
    if not key:
        if not _fernet_warned:
            logger.warning(
                "DAWN_TOKEN_ENCRYPTION_KEY is not set — MCP OAuth tokens will be "
                "stored in plaintext. Set it to encrypt tokens at rest."
            )
            _fernet_warned = True
        return None
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
    except Exception as e:
        if not _fernet_warned:
            logger.warning(f"Failed to initialize token encryption (storing plaintext): {e}")
            _fernet_warned = True
        return None
    return _fernet


def _encrypt_row(row: dict) -> dict:
    """Encrypt the sensitive fields of a token row in place."""
    fernet = _get_fernet()
    if not fernet:
        return row
    out = dict(row)
    for f in _TOKEN_FIELDS:
        val = out.get(f)
        if val:
            out[f] = fernet.encrypt(str(val).encode()).decode()
    return out


def _decrypt_row(row: dict) -> dict:
    """Decrypt the sensitive fields of a token row, if encrypted."""
    fernet = _get_fernet()
    if not fernet:
        return row
    out = dict(row)
    for f in _TOKEN_FIELDS:
        val = out.get(f)
        if val:
            try:
                out[f] = fernet.decrypt(val.encode()).decode()
            except Exception:
                # Not encrypted (e.g. written before encryption was enabled) —
                # leave as-is.
                pass
    return out

try:
    import httpx2 as httpx  # SDK auth helpers use the vendored httpx2 fork
    from mcp.client.auth.utils import (
        build_oauth_authorization_server_metadata_discovery_urls,
        build_protected_resource_metadata_discovery_urls,
        create_client_registration_request,
        create_oauth_metadata_request,
        extract_resource_metadata_from_www_auth,
        extract_scope_from_www_auth,
        get_client_metadata_scopes,
        handle_auth_metadata_response,
        handle_protected_resource_response,
        handle_registration_response,
    )
    from mcp.client.auth.oauth2 import PKCEParameters
    from mcp.shared.auth import OAuthToken
    from mcp.shared.auth_utils import resource_url_from_server_url
    from mcp.shared.inbound import MCP_PROTOCOL_VERSION_HEADER
    HAS_OAUTH = True
except ImportError:
    HAS_OAUTH = False
    httpx = None  # type: ignore


def oauth_enabled() -> bool:
    """Whether the MCP OAuth machinery is importable (mcp SDK present)."""
    return HAS_OAUTH


# ── In-memory pending flows ─────────────────────────────────────────────────
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
    resource: Optional[str] = None  # RFC 8707 resource indicator
    issuer: Optional[str] = None    # RFC 8414 issuer, for RFC 9207 validation
    server_id: Optional[str] = None  # DAWN server id, resolved from state at callback
    created_at: float = field(default_factory=time.monotonic)


_pending_flows: dict[str, PendingFlow] = {}

# Abandoned flows (user closes the popup, navigates away, AS never redirects
# back) otherwise leak a PendingFlow — including the code_verifier — in memory
# indefinitely. Sweep entries older than this.
PENDING_FLOW_TTL_SECONDS = 600  # 10 min is generous for a browser popup flow


def _sweep_expired_flows() -> None:
    now = time.monotonic()
    expired = [s for s, f in _pending_flows.items()
               if now - f.created_at > PENDING_FLOW_TTL_SECONDS]
    for s in expired:
        _pending_flows.pop(s, None)
    if expired:
        logger.info(f"Swept {len(expired)} expired OAuth pending flow(s)")


def _redirect_uri() -> str:
    """The OAuth redirect URI for DAWN's callback route."""
    base = (settings.dawn_public_url or "http://localhost:8000").rstrip("/")
    return f"{base}/mcp/oauth/callback"


# ── Token persistence (Supabase-backed) ─────────────────────────────────────

async def _load_token_row(server_id: str) -> Optional[dict]:
    import db.client as db
    supabase = db.get_db()
    res = await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").select(
        "*"
    ).eq("server_id", server_id).maybe_single().execute())
    # maybe_single() returns None when no row matches (0 rows), so guard against it.
    if not res or not res.data:
        return None
    return _decrypt_row(res.data)


async def _save_token_row(server_id: str, row: dict) -> None:
    import db.client as db
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").upsert(
        {**_encrypt_row(row), "server_id": server_id}, on_conflict="server_id"
    ).execute())


async def delete_tokens(server_id: str) -> None:
    """Remove stored OAuth tokens for a server (re-auth / revoke)."""
    import db.client as db
    supabase = db.get_db()
    await db._async_execute(lambda: supabase.table("mcp_oauth_tokens").delete().eq("server_id", server_id).execute())


async def has_oauth_tokens(server_id: str) -> bool:
    """True if this server has an OAuth token row at all (regardless of whether
    the current token is valid) — i.e. whether it's OAuth-authenticated as
    opposed to using a static key."""
    row = await _load_token_row(server_id)
    return bool(row)


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
    # RFC 8707 resource indicator — MUST be included in the token request.
    if row.get("resource"):
        data["resource"] = row["resource"]
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
        async with httpx.AsyncClient() as client:
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
        "resource": existing.get("resource"),
    }


# ── Discovery + DCR ─────────────────────────────────────────────────────────

async def _send(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    """Send an SDK-built httpx.Request and return the response."""
    return await client.send(request)


@dataclass
class OAuthDiscovery:
    """Everything learned about a server's OAuth setup during the probe."""
    auth_server_url: str          # issuer of the authorization server
    protected_resource_metadata: object  # ProtectedResourceMetadata (or None)
    authorization_server_metadata: object  # OAuthMetadata (or None)
    challenge_scope: Optional[str]  # scope from the WWW-Authenticate header


async def probe_oauth(server_url: str) -> Optional[OAuthDiscovery]:
    """Probe a server unauthenticated and detect whether it requires OAuth.

    Returns an `OAuthDiscovery` if the server advertises OAuth (via a 401
    Bearer challenge or RFC 9728 well-known metadata), else None (server uses
    static key / no auth).
    """
    if not HAS_OAUTH:
        return None
    try:
        async with httpx.AsyncClient() as client:
            # MCP streamable HTTP servers only respond to POST (JSON-RPC), not
            # GET. Send an unauthenticated `initialize` request — an
            # OAuth-protected server answers with 401 + a `WWW-Authenticate`
            # Bearer challenge carrying the protected-resource-metadata URL.
            resp = await client.post(
                server_url,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "DAWN", "version": "1.0.0"},
                    },
                },
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                    MCP_PROTOCOL_VERSION_HEADER: "2025-06-18",
                },
            )
            # Some servers allow unauthenticated `initialize` but gate
            # `tools/list` behind OAuth, so a 200 here doesn't rule OAuth out.
            # Detect OAuth in three ways:
            #   1. A 401 + WWW-Authenticate Bearer challenge on initialize.
            #   2. A 401 + WWW-Authenticate Bearer challenge on `tools/list`
            #      (the common case: initialize is open, tools are gated).
            #   3. RFC 9728 well-known protected-resource-metadata discovery
            #      (the server may publish it even when no request 401s).
            challenge_scope = None
            prm_url = None
            if resp.status_code == 401:
                www_auth = resp.headers.get("www-authenticate", "")
                if "Bearer" in www_auth:
                    prm_url = extract_resource_metadata_from_www_auth(resp)
                    challenge_scope = extract_scope_from_www_auth(resp)
            else:
                # initialize succeeded — try a gated call to surface the challenge.
                tools_resp = await client.post(
                    server_url,
                    json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    headers={
                        "accept": "application/json, text/event-stream",
                        "content-type": "application/json",
                        MCP_PROTOCOL_VERSION_HEADER: "2025-06-18",
                    },
                )
                if tools_resp.status_code == 401:
                    www_auth = tools_resp.headers.get("www-authenticate", "")
                    if "Bearer" in www_auth:
                        prm_url = extract_resource_metadata_from_www_auth(tools_resp)
                        challenge_scope = extract_scope_from_www_auth(tools_resp)
            # Always try well-known discovery as a fallback.
            prm_urls = build_protected_resource_metadata_discovery_urls(prm_url, server_url)
            prm = None
            for url in prm_urls:
                try:
                    prm_resp = await _send(client, create_oauth_metadata_request(url))
                except Exception:
                    continue
                prm = await handle_protected_resource_response(prm_resp)
                if prm and prm.authorization_servers:
                    break
            if not prm or not prm.authorization_servers:
                return None
            auth_server_url = str(prm.authorization_servers[0])
            # Fetch the authorization server metadata for the discovered issuer.
            asm = await _discover_oauth_metadata(server_url, auth_server_url)
            return OAuthDiscovery(
                auth_server_url=auth_server_url,
                protected_resource_metadata=prm,
                authorization_server_metadata=asm,
                challenge_scope=challenge_scope,
            )
    except Exception as e:
        logger.warning(f"OAuth probe failed for {server_url}: {e}")
    return None


async def _discover_oauth_metadata(server_url: str, auth_server_url: str):
    """Fetch the Authorization Server Metadata (OAuthMetadata) for the issuer."""
    if not HAS_OAUTH:
        return None
    async with httpx.AsyncClient() as client:
        for url in build_oauth_authorization_server_metadata_discovery_urls(auth_server_url, server_url):
            resp = await _send(client, create_oauth_metadata_request(url))
            ok, asm = await handle_auth_metadata_response(resp)
            if ok and asm:
                return asm
    return None


async def _register_client(server_url: str, oauth_metadata, redirect_uri: str) -> dict:
    """Register a dynamic client (DCR) against the AS metadata."""
    from mcp.shared.auth import OAuthClientMetadata
    client_metadata = OAuthClientMetadata(
        redirect_uris=[redirect_uri],
        token_endpoint_auth_method="none",
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        client_name="DAWN",
        # DAWN is a web app (browser popup + server-side callback), not a
        # native/loopback client, so advertise "web".
        application_type="web",
    )
    auth_base = _origin(server_url)
    request = create_client_registration_request(oauth_metadata, client_metadata, auth_base)
    async with httpx.AsyncClient() as client:
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


def _canonical_resource(server_url: str, prm) -> str:
    """RFC 8707 resource indicator: PRM resource if it's a valid parent of the
    server URL, else the canonical server URI."""
    try:
        if prm is not None and prm.resource:
            prm_resource = str(prm.resource)
            server_canonical = resource_url_from_server_url(server_url)
            # Prefer the PRM resource when it is a parent of the server URL.
            if server_canonical.startswith(prm_resource.rstrip("/")) or prm_resource.rstrip("/").startswith(
                server_canonical.rstrip("/")
            ):
                return prm_resource
        return resource_url_from_server_url(server_url)
    except Exception:
        return resource_url_from_server_url(server_url)


async def start_oauth_flow(server_url: str, server_id: Optional[str] = None) -> dict:
    """Run discovery + DCR and build the authorization URL for a server.

    Returns a dict with the authorization URL to open in a popup, plus the
    `state` used to correlate the callback. Raises ValueError if the server
    does not support OAuth.

    `server_id` is stored in the in-memory pending flow (keyed by `state`) so
    the callback can resolve which DAWN server the tokens belong to without
    relying on the authorization server echoing a custom `server_id` query
    param back through the redirect (many ASes strip unknown params).
    """
    if not HAS_OAUTH:
        raise ValueError("MCP OAuth support not available (mcp SDK missing)")

    # Sweep abandoned flows on the one place new ones get created — cheap, and
    # no separate background task needed for something this low-volume.
    _sweep_expired_flows()

    discovery = await probe_oauth(server_url)
    if not discovery:
        raise ValueError("Server does not require OAuth (no 401 Bearer challenge)")

    oauth_metadata = discovery.authorization_server_metadata
    if not oauth_metadata or not oauth_metadata.authorization_endpoint or not oauth_metadata.token_endpoint:
        raise ValueError("Server advertised no usable OAuth authorization/token endpoint")

    redirect_uri = _redirect_uri()
    client_info = await _register_client(server_url, oauth_metadata, redirect_uri)

    # Ensure the client we registered is one the code flow can act on.
    _check_registration_usable(client_info)

    pkce = PKCEParameters.generate()
    state = secrets.token_urlsafe(32)

    # RFC 8707 resource indicator — MUST be included in the authorization request.
    resource = _canonical_resource(server_url, discovery.protected_resource_metadata)

    # Scope selection per the MCP spec: challenge scope → PRM scopes → AS scopes,
    # plus offline_access when the AS supports it (for refresh tokens).
    scope = get_client_metadata_scopes(
        discovery.challenge_scope,
        discovery.protected_resource_metadata,
        oauth_metadata,
        client_grant_types=["authorization_code", "refresh_token"],
    )

    params = {
        "response_type": "code",
        "client_id": client_info["client_id"],
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": pkce.code_challenge,
        "code_challenge_method": "S256",
        "resource": resource,
    }
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
        resource=resource,
        issuer=str(oauth_metadata.issuer) if oauth_metadata.issuer else None,
        server_id=server_id,
    )

    return {"authorization_url": authorization_url, "state": state}


def _check_registration_usable(client_info: dict) -> None:
    """Reject a registration we cannot act on (mirrors the SDK's check)."""
    method = client_info.get("token_endpoint_auth_method")
    if method not in (None, "none", "client_secret_basic", "client_secret_post"):
        raise ValueError(f"Server registered unsupported token_endpoint_auth_method: {method!r}")
    if method in ("client_secret_basic", "client_secret_post") and not client_info.get("client_secret"):
        raise ValueError(f"Server registered for {method!r} but issued no client_secret")


async def handle_oauth_callback(server_id: Optional[str], code: str, state: str, iss: Optional[str] = None) -> dict:
    """Exchange the authorization code at the token endpoint and persist tokens.

    Validates the RFC 9207 `iss` parameter against the recorded issuer before
    exchanging the code. Returns a summary dict; raises ValueError on failure.

    `server_id` is resolved from the pending flow (keyed by `state`) when the
    authorization server did not echo it back as a query param; the explicit
    `server_id` argument is used as a fallback when it was echoed.
    """
    flow = _pending_flows.pop(state, None)
    if flow is None:
        raise ValueError("Unknown or expired OAuth state — please retry sign-in")
    if not HAS_OAUTH:
        raise ValueError("MCP OAuth support not available")

    # Resolve the DAWN server id: prefer the one stored at flow start (the
    # authoritative source), falling back to the query param the AS echoed.
    resolved_server_id = flow.server_id or server_id
    if not resolved_server_id:
        raise ValueError("Could not determine which server this OAuth flow belongs to")

    # RFC 9207 authorization-response issuer validation: if the AS advertises
    # iss support and returns one, it must match the recorded issuer.
    if flow.issuer and iss and iss != flow.issuer:
        raise ValueError("Authorization response issuer does not match the expected authorization server")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": flow.redirect_uri,
        "client_id": flow.client_id,
        "code_verifier": flow.code_verifier,
    }
    # RFC 8707 resource indicator — MUST be included in the token request.
    if flow.resource:
        data["resource"] = flow.resource
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
        async with httpx.AsyncClient() as client:
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
        "resource": flow.resource,
    }
    await _save_token_row(resolved_server_id, _token_row_from_token(token, existing))

    return {"status": "success", "server_id": resolved_server_id}
