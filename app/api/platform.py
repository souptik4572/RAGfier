from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeySummary,
    IntegrationCreateRequest,
    IntegrationListResponse,
    IntegrationSummary,
)
from app.utils.api_errors import build_response, raise_api_error
from app.utils.logger import get_logger
from app.utils.platform_observability import write_audit_log
from app.utils.platform_security import generate_api_key, hash_api_key

logger = get_logger(__name__)

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post("/integrations", response_model=IntegrationSummary, status_code=201)
async def create_integration(
    payload: IntegrationCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> IntegrationSummary:
    client = get_service_client()
    rows = (
        client.table("integrations")
        .insert(
            {
                "tenant_id": auth.tenant_id,
                "name": payload.name,
                "environment": payload.environment,
                "metadata": payload.metadata,
            }
        )
        .execute()
        .data
        or []
    )
    if not rows:
        raise_api_error(500, "platform.integration_created")
    row = rows[0]
    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="integration.created",
        resource_type="integration",
        resource_id=str(row["id"]),
    )
    return build_response(
        IntegrationSummary,
        "platform.integration_created",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        name=row["name"],
        environment=row["environment"],
        metadata=row.get("metadata") or {},
        created_at=row.get("created_at"),
    )


@router.get("/integrations", response_model=IntegrationListResponse)
async def list_integrations(
    auth: AuthContext = Depends(get_auth_context),
) -> IntegrationListResponse:
    client = get_service_client()
    rows = client.table("integrations").select("*").eq("tenant_id", auth.tenant_id).execute().data or []
    return build_response(
        IntegrationListResponse,
        "platform.integrations_listed",
        integrations=[
            IntegrationSummary(
                message="",
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                name=row["name"],
                environment=row.get("environment") or "production",
                metadata=row.get("metadata") or {},
                created_at=row.get("created_at"),
            ).model_dump(mode="json")
            for row in rows
        ],
    )


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_api_key(
    payload: ApiKeyCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> ApiKeyCreateResponse:
    client = get_service_client()
    integration = (
        client.table("integrations")
        .select("*")
        .eq("tenant_id", auth.tenant_id)
        .eq("id", str(payload.integration_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not integration:
        raise_api_error(404, "platform.integration_not_found")

    prefix, secret = generate_api_key()
    rows = (
        client.table("api_keys")
        .insert(
            {
                "tenant_id": auth.tenant_id,
                "integration_id": str(payload.integration_id),
                "name": payload.name,
                "prefix": prefix,
                "secret_hash": hash_api_key(secret),
                "scopes": payload.scopes,
                "status": "active",
                "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
            }
        )
        .execute()
        .data
        or []
    )
    if not rows:
        raise_api_error(500, "platform.api_key_created")
    row = rows[0]
    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="api_key.created",
        resource_type="api_key",
        resource_id=str(row["id"]),
        metadata={"integration_id": str(payload.integration_id), "scopes": payload.scopes},
    )
    return build_response(
        ApiKeyCreateResponse,
        "platform.api_key_created",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        integration_id=UUID(str(row["integration_id"])),
        name=row["name"],
        prefix=row["prefix"],
        secret=secret,
        scopes=row.get("scopes") or [],
        status=row["status"],
        expires_at=row.get("expires_at"),
        last_used_at=row.get("last_used_at"),
        created_at=row.get("created_at"),
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    auth: AuthContext = Depends(get_auth_context),
) -> ApiKeyListResponse:
    client = get_service_client()
    rows = client.table("api_keys").select("*").eq("tenant_id", auth.tenant_id).execute().data or []
    return build_response(
        ApiKeyListResponse,
        "platform.api_keys_listed",
        api_keys=[
            ApiKeySummary(
                message="",
                id=UUID(str(row["id"])),
                tenant_id=UUID(str(row["tenant_id"])),
                integration_id=UUID(str(row["integration_id"])),
                name=row["name"],
                prefix=row["prefix"],
                scopes=row.get("scopes") or [],
                status=row["status"],
                expires_at=row.get("expires_at"),
                last_used_at=row.get("last_used_at"),
                created_at=row.get("created_at"),
            ).model_dump(mode="json")
            for row in rows
        ],
    )


@router.post("/api-keys/{api_key_id}/revoke", response_model=ApiKeySummary)
async def revoke_api_key(
    api_key_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> ApiKeySummary:
    client = get_service_client()
    rows = (
        client.table("api_keys")
        .select("*")
        .eq("tenant_id", auth.tenant_id)
        .eq("id", str(api_key_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise_api_error(404, "platform.api_key_not_found")

    client.table("api_keys").update({"status": "revoked", "revoked_at": "now()"}).eq("id", str(api_key_id)).execute()
    row = rows[0]
    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="api_key.revoked",
        resource_type="api_key",
        resource_id=str(api_key_id),
    )
    return build_response(
        ApiKeySummary,
        "platform.api_key_revoked",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        integration_id=UUID(str(row["integration_id"])),
        name=row["name"],
        prefix=row["prefix"],
        scopes=row.get("scopes") or [],
        status="revoked",
        expires_at=row.get("expires_at"),
        last_used_at=row.get("last_used_at"),
        created_at=row.get("created_at"),
    )
