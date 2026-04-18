from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.auth import AuthContext, get_auth_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeySummary,
    CountResponse,
    IntegrationCreateRequest,
    IntegrationDeleteResponse,
    IntegrationListResponse,
    IntegrationSummary,
    IntegrationUpdateRequest,
)
from app.utils.api_errors import build_response, raise_api_error
from app.utils.logger import get_logger
from app.utils.platform_observability import write_audit_log, write_audit_log_async
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


@router.get("/integrations/count", response_model=CountResponse)
async def count_integrations(
    auth: AuthContext = Depends(get_auth_context),
) -> CountResponse:
    client = get_service_client()
    rows = (
        client.table("integrations")
        .select("id")
        .eq("tenant_id", auth.tenant_id)
        .execute()
        .data
        or []
    )
    return build_response(
        CountResponse,
        "platform.integrations_counted",
        count=len(rows),
    )


@router.get("/api-keys/count", response_model=CountResponse)
async def count_api_keys(
    auth: AuthContext = Depends(get_auth_context),
) -> CountResponse:
    client = get_service_client()
    rows = (
        client.table("api_keys")
        .select("id")
        .eq("tenant_id", auth.tenant_id)
        .eq("status", "active")
        .execute()
        .data
        or []
    )
    return build_response(
        CountResponse,
        "platform.api_keys_counted",
        count=len(rows),
    )


@router.get("/integrations/{integration_id}", response_model=IntegrationSummary)
async def get_integration(
    integration_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> IntegrationSummary:
    client = get_service_client()
    rows = (
        client.table("integrations")
        .select("*")
        .eq("tenant_id", auth.tenant_id)
        .eq("id", str(integration_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise_api_error(404, "platform.integration_not_found")
    row = rows[0]
    return build_response(
        IntegrationSummary,
        "platform.integration_fetched",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        name=row["name"],
        environment=row.get("environment") or "production",
        metadata=row.get("metadata") or {},
        created_at=row.get("created_at"),
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


@router.patch("/integrations/{integration_id}", response_model=IntegrationSummary)
async def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> IntegrationSummary:
    client = get_service_client()
    existing = (
        client.table("integrations")
        .select("*")
        .eq("tenant_id", auth.tenant_id)
        .eq("id", str(integration_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not existing:
        raise_api_error(404, "platform.integration_not_found")

    updates: dict[str, Any] = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.environment is not None:
        updates["environment"] = payload.environment
    if payload.metadata is not None:
        updates["metadata"] = payload.metadata
    if payload.is_default is True:
        # Clear any existing default to avoid violating the partial unique
        # index on (tenant_id) WHERE is_default = TRUE.
        client.table("integrations").update({"is_default": False}).eq(
            "tenant_id", auth.tenant_id
        ).eq("is_default", True).execute()
        updates["is_default"] = True
    elif payload.is_default is False:
        updates["is_default"] = False

    if updates:
        client.table("integrations").update(updates).eq(
            "id", str(integration_id)
        ).eq("tenant_id", auth.tenant_id).execute()

    refreshed = (
        client.table("integrations")
        .select("*")
        .eq("id", str(integration_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    row = refreshed[0] if refreshed else existing[0]

    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="integration.updated",
        resource_type="integration",
        resource_id=str(integration_id),
        metadata={"fields": list(updates.keys())},
    )
    return build_response(
        IntegrationSummary,
        "platform.integration_updated",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        name=row["name"],
        environment=row.get("environment") or "production",
        metadata=row.get("metadata") or {},
        created_at=row.get("created_at"),
    )


@router.delete("/integrations/{integration_id}", response_model=IntegrationDeleteResponse)
async def delete_integration(
    integration_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> IntegrationDeleteResponse:
    client = get_service_client()
    existing = (
        client.table("integrations")
        .select("id")
        .eq("tenant_id", auth.tenant_id)
        .eq("id", str(integration_id))
        .limit(1)
        .execute()
        .data
        or []
    )
    if not existing:
        raise_api_error(404, "platform.integration_not_found")

    # 1) Gather ingestion jobs to collect storage paths and drive document deletion.
    jobs = (
        client.table("ingestion_jobs")
        .select("id, file_path")
        .eq("tenant_id", auth.tenant_id)
        .eq("integration_id", str(integration_id))
        .execute()
        .data
        or []
    )
    job_ids = [str(j["id"]) for j in jobs]
    storage_paths = [
        str(j["file_path"])
        for j in jobs
        if j.get("file_path") and not str(j["file_path"]).startswith("local://")
    ]

    # 2) Delete embedded chunks (documents) belonging to those jobs.
    deleted_documents = 0
    if job_ids:
        doc_rows = (
            client.table("documents")
            .delete()
            .in_("job_id", job_ids)
            .execute()
            .data
            or []
        )
        deleted_documents = len(doc_rows)

    # 3) Delete ingestion_jobs rows. documents.integration_id has ON DELETE
    # SET NULL, so any lingering rows still referencing the integration are
    # dropped here as well as a safeguard.
    deleted_jobs = 0
    if job_ids:
        job_deleted = (
            client.table("ingestion_jobs")
            .delete()
            .in_("id", job_ids)
            .execute()
            .data
            or []
        )
        deleted_jobs = len(job_deleted)

    # 4) Best-effort remove storage objects (Supabase bucket).
    deleted_storage_objects = 0
    if storage_paths:
        try:
            settings = get_settings()
            client.storage.from_(settings.supabase_storage_bucket).remove(storage_paths)
            deleted_storage_objects = len(storage_paths)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "platform.integration_delete.storage_cleanup_failed",
                integration_id=str(integration_id),
                error=str(exc),
            )

    # 5) Snapshot api_key count before the FK cascade removes them.
    api_key_rows = (
        client.table("api_keys")
        .select("id")
        .eq("tenant_id", auth.tenant_id)
        .eq("integration_id", str(integration_id))
        .execute()
        .data
        or []
    )
    deleted_api_keys = len(api_key_rows)

    # 6) Delete the integration. api_keys cascade via FK ON DELETE CASCADE.
    client.table("integrations").delete().eq("id", str(integration_id)).eq(
        "tenant_id", auth.tenant_id
    ).execute()

    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="integration.deleted",
        resource_type="integration",
        resource_id=str(integration_id),
        metadata={
            "deleted_documents": deleted_documents,
            "deleted_jobs": deleted_jobs,
            "deleted_api_keys": deleted_api_keys,
            "deleted_storage_objects": deleted_storage_objects,
        },
    )
    logger.info(
        "platform.integration_deleted",
        tenant_id=auth.tenant_id,
        integration_id=str(integration_id),
        deleted_documents=deleted_documents,
        deleted_jobs=deleted_jobs,
        deleted_api_keys=deleted_api_keys,
        deleted_storage_objects=deleted_storage_objects,
    )
    return build_response(
        IntegrationDeleteResponse,
        "platform.integration_deleted",
        integration_id=integration_id,
        deleted_documents=deleted_documents,
        deleted_jobs=deleted_jobs,
        deleted_api_keys=deleted_api_keys,
        deleted_storage_objects=deleted_storage_objects,
    )
