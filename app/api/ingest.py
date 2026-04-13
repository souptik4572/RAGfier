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
    auth: AuthContext = Depends(get_auth_context),
) -> IngestResponse:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(status_code=422, detail="File must have a name.")

    file_type = _detect_file_type(file.filename)
    if file_type not in settings.allowed_file_types:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type: {file_type}. "
            f"Allowed: {', '.join(settings.allowed_file_types)}",
        )

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(contents) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {settings.max_file_size_mb} MB limit.",
        )

    job_id = str(uuid.uuid4())
    storage_path = f"{auth.tenant_id}/{job_id}/{file.filename}"

    # Upload the raw file to Supabase Storage (best-effort — if not
    # configured we still proceed to local processing).
    try:
        client = get_service_client()
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
        client = get_service_client()
        client.table("ingestion_jobs").insert(
            {
                "id": job_id,
                "tenant_id": auth.tenant_id,
                "file_name": file.filename,
                "file_path": storage_path,
                "status": "pending",
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
        raise HTTPException(
            status_code=500, detail="Failed to create ingestion job."
        ) from exc

    background_tasks.add_task(
        run_pipeline_task,
        job_id=job_id,
        tenant_id=auth.tenant_id,
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

    return IngestResponse(
        job_id=uuid.UUID(job_id),
        status="pending",
        message="Ingestion pipeline started",
    )
