from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    supabase_status = "not_configured"
    if settings.supabase_url and settings.supabase_service_role_key:
        try:
            get_service_client()
            supabase_status = "connected"
        except Exception:
            supabase_status = "error"

    openai_status = "configured" if settings.openai_api_key else "not_configured"
    cohere_status = "configured" if settings.cohere_api_key else "not_configured"

    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        supabase=supabase_status,
        openai=openai_status,
        cohere=cohere_status,
    )
