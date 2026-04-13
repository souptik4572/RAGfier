from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import JobStatusResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["status"])


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
) -> JobStatusResponse:
    client = get_service_client()
    try:
        result = (
            client.table("ingestion_jobs")
            .select("*")
            .eq("id", str(job_id))
            .eq("tenant_id", auth.tenant_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.error(
            "status.query_failed",
            job_id=str(job_id),
            tenant_id=auth.tenant_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to query job status.") from exc

    rows = result.data or []
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found for this tenant.",
        )
    row = rows[0]
    return JobStatusResponse(
        job_id=UUID(row["id"]),
        status=row["status"],
        file_name=row["file_name"],
        total_chunks=row.get("total_chunks") or 0,
        processed_chunks=row.get("processed_chunks") or 0,
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
