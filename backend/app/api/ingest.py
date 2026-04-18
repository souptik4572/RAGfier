from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)

from app.api.auth import AuthContext, get_auth_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import IngestResponse
from app.pipeline.orchestrator import run_pipeline_task
from app.utils.api_errors import build_response, raise_api_error
from app.utils.integration_resolver import resolve_integration
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["ingest"])


def _detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return suffix


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_title: Optional[str] = Form(default=None),
    integration_id: Optional[str] = Form(default=None),
    auth: AuthContext = Depends(get_auth_context),
) -> IngestResponse:
    settings = get_settings()
    client = get_service_client()
    integration = resolve_integration(client, auth.tenant_id, integration_id)
    resolved_integration_id = str(integration["id"])

    if not file.filename:
        raise_api_error(422, "ingest.file_name_required")

    file_type = _detect_file_type(file.filename)
    if file_type not in settings.allowed_file_types:
        raise_api_error(
            422,
            "ingest.unsupported_file_type",
            detail={
                "file_type": file_type,
                "allowed_file_types": settings.allowed_file_types,
            },
        )

    contents = await file.read()
    if len(contents) == 0:
        raise_api_error(422, "ingest.empty_file")
    if len(contents) > settings.max_file_size_bytes:
        raise_api_error(
            413,
            "ingest.file_too_large",
            detail={"max_file_size_mb": settings.max_file_size_mb},
        )

    job_id = str(uuid.uuid4())
    storage_path = f"{auth.tenant_id}/{resolved_integration_id}/{job_id}/{file.filename}"

    # Upload the raw file to Supabase Storage (best-effort — if not
    # configured we still proceed to local processing).
    try:
        client.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        logger.warning(
            "ingest.storage_upload_failed",
            tenant_id=auth.tenant_id,
            job_id=job_id,
            error=str(exc),
        )
        storage_path = f"local://{file.filename}"

    # Persist the raw bytes to a temp file so the background pipeline
    # can parse without needing to re-download from Storage.
    tmp_dir = Path(tempfile.gettempdir()) / "ragfier" / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / file.filename
    tmp_file.write_bytes(contents)

    # Create the ingestion_jobs row.
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
        logger.error(
            "ingest.job_create_failed",
            tenant_id=auth.tenant_id,
            job_id=job_id,
            error=str(exc),
        )
        raise_api_error(500, "ingest.job_create_failed")

    background_tasks.add_task(
        run_pipeline_task,
        job_id=job_id,
        tenant_id=auth.tenant_id,
        integration_id=resolved_integration_id,
        file_path=str(tmp_file),
        file_name=file.filename,
        file_type=file_type,
        document_title=document_title,
    )

    logger.info(
        "ingest.accepted",
        tenant_id=auth.tenant_id,
        job_id=job_id,
        file_name=file.filename,
        file_size=len(contents),
    )

    return build_response(
        IngestResponse,
        "ingest.accepted",
        job_id=uuid.UUID(job_id),
        status="pending",
        integration_id=uuid.UUID(resolved_integration_id),
    )
