from __future__ import annotations

from typing import Any, Optional

from app.utils.api_errors import raise_api_error
from app.utils.logger import get_logger

logger = get_logger(__name__)

_DEFAULT_INTEGRATION_NAME = "Default"
_DEFAULT_INTEGRATION_ENV = "production"


def get_or_create_default_integration(client: Any, tenant_id: str) -> dict:
    """Return the tenant's default global integration, creating it if absent."""
    rows = (
        client.table("integrations")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_default", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if rows:
        return rows[0]

    rows = (
        client.table("integrations")
        .insert(
            {
                "tenant_id": tenant_id,
                "name": _DEFAULT_INTEGRATION_NAME,
                "environment": _DEFAULT_INTEGRATION_ENV,
                "metadata": {},
                "is_default": True,
            }
        )
        .execute()
        .data
        or []
    )
    if not rows:
        raise_api_error(500, "platform.default_integration_create_failed")
    logger.info("platform.default_integration_created", tenant_id=tenant_id)
    return rows[0]


def resolve_integration(
    client: Any,
    tenant_id: str,
    integration_id: Optional[str],
) -> dict:
    """Resolve integration_id to a row, falling back to the default.

    Priority:
    1. Explicit integration_id — must belong to this tenant (404 if not).
    2. Tenant default global integration (auto-created if missing).
    """
    if integration_id:
        rows = (
            client.table("integrations")
            .select("*")
            .eq("tenant_id", tenant_id)
            .eq("id", integration_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            raise_api_error(404, "platform.integration_not_found")
        return rows[0]

    return get_or_create_default_integration(client, tenant_id)
