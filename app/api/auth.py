from __future__ import annotations

import base64
import json
from typing import Optional

from fastapi import Header, HTTPException, status

from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuthContext:
    """Resolved identity attached to an authenticated request."""

    def __init__(self, tenant_id: str, user_id: Optional[str] = None) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id


def _decode_jwt_claims(token: str) -> dict:
    """Decode JWT payload *without* verifying the signature.

    Signature verification is delegated to Supabase (the `anon` and
    `authenticated` keys enforce RLS on the DB side). This helper only
    extracts `app_metadata.organization_id` for routing.
    """
    try:
        _, payload_b64, _ = token.split(".")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT",
        ) from exc
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT payload",
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT payload must be an object",
        )
    return payload


async def get_auth_context(
    authorization: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
) -> AuthContext:
    """Extract tenant identity from the `Authorization: Bearer` header.

    An `X-Tenant-Id` header override is accepted to ease local testing;
    production deployments should rely exclusively on the JWT.
    """
    if x_tenant_id:
        return AuthContext(tenant_id=x_tenant_id)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_jwt_claims(token)
    app_metadata = claims.get("app_metadata") or {}
    tenant_id = app_metadata.get("organization_id")
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="JWT missing app_metadata.organization_id",
        )
    user_id = claims.get("sub")
    return AuthContext(tenant_id=str(tenant_id), user_id=user_id)
