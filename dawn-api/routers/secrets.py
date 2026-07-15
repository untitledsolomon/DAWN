"""DAWN Secrets API — encrypted storage for API keys, tokens, and auth credentials.

Secrets are encrypted at rest using Fernet (symmetric encryption) with a key
derived from the DAWN_API_KEY. This means only the DAWN API itself can decrypt
them — the database stores ciphertext only.

The agent can read secrets at runtime via the `get_secret` tool, so you never
need to paste tokens into the sandbox or conversation again.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from typing import Optional
from config import settings
import db.client as db
import hashlib
import base64
from cryptography.fernet import Fernet

router = APIRouter()


def verify_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != settings.dawn_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ── Encryption ──────────────────────────────────────────────────────────────

def _derive_fernet_key() -> bytes:
    """Derive a 32-byte Fernet key from the DAWN_API_KEY.

    Uses SHA-256 so any length API key produces a valid 32-byte key,
    then base64-url-encodes it as Fernet requires.
    """
    raw = hashlib.sha256(settings.dawn_api_key.encode()).digest()
    return base64.urlsafe_b64encode(raw)


def _encrypt(plaintext: str) -> str:
    key = _derive_fernet_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    key = _derive_fernet_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()


# ── Schema ──────────────────────────────────────────────────────────────────

class SecretCreate(BaseModel):
    name: str
    value: str
    description: Optional[str] = None
    tags: list[str] = []


class SecretUpdate(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class SecretResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: list[str]
    created_at: str
    updated_at: str
    # NEVER include the decrypted value in list responses


class SecretValueResponse(BaseModel):
    id: str
    name: str
    value: str
    description: Optional[str] = None
    tags: list[str]
    created_at: str
    updated_at: str


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/", response_model=list[SecretResponse])
async def list_secrets(
    tag: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    _: None = Depends(verify_key),
):
    """List stored secrets (values are NEVER returned in list view)."""
    secrets = await db.list_secrets(tag=tag, limit=limit, offset=offset)
    # Strip the encrypted value from list responses
    result = []
    for s in secrets:
        result.append({
            "id": s["id"],
            "name": s["name"],
            "description": s.get("description"),
            "tags": s.get("tags", []),
            "created_at": s["created_at"],
            "updated_at": s["updated_at"],
        })
    return result


@router.get("/count")
async def count_secrets(
    _: None = Depends(verify_key),
):
    """Return the total number of stored secrets."""
    total = await db.count_secrets()
    return {"total": total}


@router.post("/", response_model=SecretResponse)
async def create_secret(payload: SecretCreate, _: None = Depends(verify_key)):
    """Store a new secret (encrypted at rest)."""
    encrypted_value = _encrypt(payload.value)
    secret = await db.create_secret(
        name=payload.name,
        encrypted_value=encrypted_value,
        description=payload.description,
        tags=payload.tags,
    )
    if not secret.get("id"):
        raise HTTPException(status_code=500, detail="Secret creation failed")
    return {
        "id": secret["id"],
        "name": secret["name"],
        "description": secret.get("description"),
        "tags": secret.get("tags", []),
        "created_at": secret["created_at"],
        "updated_at": secret["updated_at"],
    }


@router.get("/{secret_id}", response_model=SecretValueResponse)
async def get_secret(secret_id: str, _: None = Depends(verify_key)):
    """Get a single secret with its decrypted value."""
    secret = await db.get_secret_by_id(secret_id)
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    try:
        decrypted = _decrypt(secret["encrypted_value"])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt secret")
    return {
        "id": secret["id"],
        "name": secret["name"],
        "value": decrypted,
        "description": secret.get("description"),
        "tags": secret.get("tags", []),
        "created_at": secret["created_at"],
        "updated_at": secret["updated_at"],
    }


@router.put("/{secret_id}", response_model=SecretResponse)
async def update_secret(
    secret_id: str,
    payload: SecretUpdate,
    _: None = Depends(verify_key),
):
    """Update a secret (re-encrypts if value is provided)."""
    data = {}
    if payload.name is not None:
        data["name"] = payload.name
    if payload.value is not None:
        data["encrypted_value"] = _encrypt(payload.value)
    if payload.description is not None:
        data["description"] = payload.description
    if payload.tags is not None:
        data["tags"] = payload.tags

    secret = await db.update_secret(secret_id, data)
    if not secret:
        raise HTTPException(status_code=404, detail="Secret not found")
    return {
        "id": secret["id"],
        "name": secret["name"],
        "description": secret.get("description"),
        "tags": secret.get("tags", []),
        "created_at": secret["created_at"],
        "updated_at": secret["updated_at"],
    }


@router.delete("/{secret_id}")
async def delete_secret(secret_id: str, _: None = Depends(verify_key)):
    """Delete a secret."""
    await db.delete_secret(secret_id)
    return {"deleted": secret_id}


# ── Agent-facing tool endpoint ──────────────────────────────────────────────

class SecretLookup(BaseModel):
    name: Optional[str] = None
    secret_id: Optional[str] = None


@router.post("/lookup", response_model=Optional[SecretValueResponse])
async def lookup_secret(payload: SecretLookup, _: None = Depends(verify_key)):
    """Look up a secret by name or ID (returns decrypted value).

    This is the endpoint the agent calls at runtime to fetch credentials.
    Only one of `name` or `secret_id` should be provided.
    """
    if not payload.name and not payload.secret_id:
        raise HTTPException(status_code=400, detail="Provide either 'name' or 'secret_id'")

    secret = None
    if payload.secret_id:
        secret = await db.get_secret_by_id(payload.secret_id)
    elif payload.name:
        secret = await db.get_secret_by_name(payload.name)

    if not secret:
        return None

    try:
        decrypted = _decrypt(secret["encrypted_value"])
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt secret")

    return {
        "id": secret["id"],
        "name": secret["name"],
        "value": decrypted,
        "description": secret.get("description"),
        "tags": secret.get("tags", []),
        "created_at": secret["created_at"],
        "updated_at": secret["updated_at"],
    }
