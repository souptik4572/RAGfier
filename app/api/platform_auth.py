from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import Depends, Header, status

from app.models.database import get_service_client
from app.utils.api_errors import raise_api_error
from app.utils.logger import get_logger
from app.utils.platform_security import derive_api_key_prefix, hash_api_key

logger = get_logger(__name__)


@dataclass
class PlatformAuthContext:
    tenant_id: str
    integration_id: str
    api_key_id: str
    api_key_prefix: str
    scopes: list[str] = field(default_factory=list)
    request_metadata: dict[str, Any] = field(default_factory=dict)


def require_platform_context(*required_scopes: str) -> Callable[..., PlatformAuthContext]:
    async def _dependency(
        authorization: Optional[str] = Header(default=None),
    ) -> PlatformAuthContext:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "platform_auth.missing_api_key")

        secret = authorization.split(" ", 1)[1].strip()
        try:
            prefix = derive_api_key_prefix(secret)
        except ValueError:
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "platform_auth.invalid_api_key")

        client = get_service_client()
        try:
            rows = (
                client.table("api_keys")
                .select("*")
                .eq("prefix", prefix)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as exc:
            logger.error("platform_auth.lookup_failed", prefix=prefix, error=str(exc))
            raise_api_error(500, "platform_auth.lookup_failed")

        if not rows:
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "platform_auth.invalid_api_key")

        row = rows[0]
        if row.get("status") != "active":
            raise_api_error(status.HTTP_403_FORBIDDEN, "platform_auth.api_key_inactive")
        if row.get("expires_at") and _is_expired(str(row["expires_at"])):
            raise_api_error(status.HTTP_403_FORBIDDEN, "platform_auth.api_key_expired")
        if hash_api_key(secret) != row.get("secret_hash"):
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "platform_auth.invalid_api_key")

        scopes = [str(scope) for scope in row.get("scopes") or []]
        missing = [scope for scope in required_scopes if scope not in scopes]
        if missing:
            raise_api_error(
                status.HTTP_403_FORBIDDEN,
                "platform_auth.insufficient_scope",
                detail={"missing_scopes": missing},
            )

        try:
            client.table("api_keys").update({"last_used_at": "now()"}).eq("id", row["id"]).execute()
        except Exception as exc:  # pragma: no cover - non-fatal
            logger.warning("platform_auth.last_used_update_failed", api_key_id=row.get("id"), error=str(exc))

        return PlatformAuthContext(
            tenant_id=str(row["tenant_id"]),
            integration_id=str(row["integration_id"]),
            api_key_id=str(row["id"]),
            api_key_prefix=str(row["prefix"]),
            scopes=scopes,
        )

    return _dependency


def _is_expired(value: str) -> bool:
    normalized = value.replace("Z", "+00:00")
    expires_at = datetime.fromisoformat(normalized)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
