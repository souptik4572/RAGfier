from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import (
    PromptCreateRequest,
    PromptListResponse,
    PromptSummary,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["prompts"])


def _rows_to_summaries(rows: list[Dict[str, Any]]) -> list[PromptSummary]:
    summaries: list[PromptSummary] = []
    for row in rows:
        summaries.append(
            PromptSummary(
                id=UUID(str(row["id"])),
                name=row["name"],
                version=int(row.get("version") or 1),
                is_active=bool(row.get("is_active")),
                tenant_id=UUID(str(row["tenant_id"])) if row.get("tenant_id") else None,
                metadata=row.get("metadata") or {},
                created_at=row.get("created_at"),
            )
        )
    return summaries


@router.get("/prompts", response_model=PromptListResponse)
async def list_prompts(
    auth: AuthContext = Depends(get_auth_context),
) -> PromptListResponse:
    client = get_service_client()
    try:
        tenant_rows = (
            client.table("prompt_versions")
            .select("*")
            .eq("tenant_id", auth.tenant_id)
            .execute()
            .data
            or []
        )
        global_rows = (
            client.table("prompt_versions")
            .select("*")
            .is_("tenant_id", "null")
            .execute()
            .data
            if hasattr(client.table("prompt_versions"), "is_")
            else []
        )
    except Exception as exc:
        logger.error("prompts.list_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to list prompts.") from exc

    return PromptListResponse(
        prompts=_rows_to_summaries(list(tenant_rows) + list(global_rows or []))
    )


@router.post("/prompts", response_model=PromptSummary, status_code=201)
async def create_prompt(
    payload: PromptCreateRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> PromptSummary:
    client = get_service_client()
    tenant_id: Optional[str] = None if payload.global_ else auth.tenant_id

    # Deactivate previous active prompt with the same (tenant_id, name).
    try:
        update_query = (
            client.table("prompt_versions")
            .update({"is_active": False})
            .eq("name", payload.name)
        )
        if tenant_id is None:
            update_query = (
                update_query.is_("tenant_id", "null")
                if hasattr(update_query, "is_")
                else update_query.eq("tenant_id", None)
            )
        else:
            update_query = update_query.eq("tenant_id", tenant_id)
        update_query.execute()
    except Exception as exc:  # pragma: no cover - non-fatal
        logger.warning("prompts.deactivate_previous_failed", error=str(exc))

    # Determine next version number.
    next_version = 1
    try:
        existing = (
            client.table("prompt_versions")
            .select("version")
            .eq("name", payload.name)
            .execute()
            .data
            or []
        )
        if existing:
            next_version = max(int(r.get("version") or 1) for r in existing) + 1
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("prompts.version_lookup_failed", error=str(exc))

    record = {
        "tenant_id": tenant_id,
        "name": payload.name,
        "version": next_version,
        "system_prompt": payload.system_prompt,
        "user_prompt_template": payload.user_prompt_template,
        "metadata": payload.metadata,
        "is_active": True,
    }
    try:
        response = client.table("prompt_versions").insert(record).execute()
    except Exception as exc:
        logger.error("prompts.insert_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to create prompt.") from exc

    rows = response.data or []
    if not rows:
        raise HTTPException(status_code=500, detail="Prompt insert returned no row.")
    return _rows_to_summaries(rows)[0]
