from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from app.api._query_shared import build_stream_response, execute_query
from app.api.auth import AuthContext, get_auth_context
from app.api.platform_auth import PlatformAuthContext, require_platform_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentSummary,
    IntegrationQueryRequest,
    IntegrationQueryResponse,
    IngestResponse,
)
from app.utils.api_errors import build_response, raise_api_error
from app.utils.integration_resolver import resolve_integration
from app.utils.logger import get_logger
from app.utils.platform_observability import write_audit_log_async

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/integrations", tags=["integrations"])


# ── JWT-authenticated document management ─────────────────────────────────────

@router.post(
    "/{integration_id}/documents",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document_to_integration(
    integration_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_title: Optional[str] = Form(default=None),
    auth: AuthContext = Depends(get_auth_context),
) -> IngestResponse:
    from app.pipeline.orchestrator import run_pipeline_task

    client = get_service_client()
    integration = resolve_integration(client, auth.tenant_id, str(integration_id))
    resolved_integration_id = str(integration["id"])

    settings = get_settings()
    if not file.filename:
        raise_api_error(422, "ingest.file_name_required")
    file_name = file.filename or ""

    file_type = settings.canonical_file_type(file_name)
    if file_type not in settings.allowed_file_types:
        raise_api_error(
            422,
            "ingest.unsupported_file_type",
            detail={
                "file_type": file_type,
                "allowed_file_types": settings.allowed_file_types,
                "allowed_file_extensions": settings.allowed_file_extensions,
            },
        )

    contents = await file.read()
    if not contents:
        raise_api_error(422, "ingest.empty_file")
    if len(contents) > settings.max_file_size_bytes:
        raise_api_error(413, "ingest.file_too_large", detail={"max_file_size_mb": settings.max_file_size_mb})

    job_id = str(uuid.uuid4())
    storage_path = f"{auth.tenant_id}/{resolved_integration_id}/{job_id}/{file_name}"
    try:
        client.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        logger.warning("integrations.upload.storage_failed", tenant_id=auth.tenant_id, job_id=job_id, error=str(exc))
        storage_path = f"local://{file_name}"

    tmp_dir = Path(tempfile.gettempdir()) / "ragfier" / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / file_name
    tmp_file.write_bytes(contents)

    try:
        client.table("ingestion_jobs").insert(
            {
                "id": job_id,
                "tenant_id": auth.tenant_id,
                "integration_id": resolved_integration_id,
                "file_name": file.filename,
                "file_path": storage_path,
                "status": "pending",
                "source_type": "upload",
                "metadata": {"document_title": document_title} if document_title else {},
            }
        ).execute()
    except Exception as exc:
        logger.error("integrations.job_create_failed", tenant_id=auth.tenant_id, job_id=job_id, error=str(exc))
        raise_api_error(500, "ingest.job_create_failed")

    background_tasks.add_task(
        run_pipeline_task,
        job_id=job_id,
        tenant_id=auth.tenant_id,
        integration_id=resolved_integration_id,
        file_path=str(tmp_file),
        file_name=file_name,
        file_type=file_type,
        document_title=document_title,
    )

    logger.info(
        "integrations.document_uploaded",
        tenant_id=auth.tenant_id,
        integration_id=resolved_integration_id,
        job_id=job_id,
        file_name=file_name,
    )
    return build_response(
        IngestResponse,
        "platform.document_uploaded",
        job_id=UUID(job_id),
        status="pending",
        integration_id=UUID(resolved_integration_id),
    )


@router.get("/{integration_id}/documents", response_model=DocumentListResponse)
async def list_documents_for_integration(
    integration_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> DocumentListResponse:
    client = get_service_client()
    integration = resolve_integration(client, auth.tenant_id, str(integration_id))
    resolved_integration_id = str(integration["id"])

    rows = (
        client.table("ingestion_jobs")
        .select("*")
        .eq("tenant_id", auth.tenant_id)
        .eq("integration_id", resolved_integration_id)
        .execute()
        .data
        or []
    )
    docs = [
        DocumentSummary(
            message="",
            id=str(row["id"]),
            tenant_id=UUID(str(row["tenant_id"])),
            integration_id=UUID(resolved_integration_id),
            file_name=str(row["file_name"]),
            document_title=(row.get("metadata") or {}).get("document_title"),
            source_type=row.get("source_type"),
            status=str(row.get("status") or "pending"),
            chunk_count=int(row.get("processed_chunks") or 0),
            created_at=row.get("created_at"),
        ).model_dump(mode="json")
        for row in rows
        if row.get("status") != "deleted"
    ]
    return build_response(DocumentListResponse, "platform.documents_listed", documents=docs)


@router.delete(
    "/{integration_id}/documents/{document_id}",
    response_model=DocumentDeleteResponse,
)
async def delete_document_from_integration(
    integration_id: UUID,
    document_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> DocumentDeleteResponse:
    client = get_service_client()
    integration = resolve_integration(client, auth.tenant_id, str(integration_id))
    resolved_integration_id = str(integration["id"])

    job_rows = (
        client.table("ingestion_jobs")
        .select("id")
        .eq("id", str(document_id))
        .eq("tenant_id", auth.tenant_id)
        .eq("integration_id", resolved_integration_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not job_rows:
        raise_api_error(404, "platform.document_not_found")

    deleted_chunks = (
        client.table("documents")
        .delete()
        .eq("job_id", str(document_id))
        .execute()
        .data
        or []
    )
    client.table("ingestion_jobs").update({"status": "deleted"}).eq(
        "id", str(document_id)
    ).execute()

    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="dashboard_user",
        actor_id=auth.user_id,
        action="document.deleted",
        resource_type="document",
        resource_id=str(document_id),
        metadata={
            "integration_id": resolved_integration_id,
            "deleted_chunks": len(deleted_chunks),
        },
    )

    logger.info(
        "integrations.document_deleted",
        tenant_id=auth.tenant_id,
        integration_id=resolved_integration_id,
        document_id=str(document_id),
        deleted_chunks=len(deleted_chunks),
    )
    return build_response(
        DocumentDeleteResponse,
        "platform.document_deleted",
        document_id=str(document_id),
        deleted_chunks=len(deleted_chunks),
    )


# ── API-key-authenticated query endpoints ──────────────────────────────────────

@router.post("/{integration_id}/query", response_model=IntegrationQueryResponse)
async def query_integration(
    integration_id: UUID,
    payload: IntegrationQueryRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("query:read")),
) -> IntegrationQueryResponse:
    # The API key is already scoped to an integration. Verify path matches key.
    if str(integration_id) != auth.integration_id:
        raise_api_error(403, "platform_auth.integration_mismatch")

    return await execute_query(
        payload=payload,
        auth=auth,
        client=get_service_client(),
        response_model=IntegrationQueryResponse,
        endpoint=f"/v1/integrations/{integration_id}/query",
        log_prefix="integrations.query",
    )


@router.post("/{integration_id}/query/stream")
async def query_integration_stream(
    integration_id: UUID,
    payload: IntegrationQueryRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("query:read")),
) -> EventSourceResponse:
    if str(integration_id) != auth.integration_id:
        raise_api_error(403, "platform_auth.integration_mismatch")

    return await build_stream_response(
        payload=payload,
        auth=auth,
        client=get_service_client(),
        endpoint=f"/v1/integrations/{integration_id}/query/stream",
    )
