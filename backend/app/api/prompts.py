from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import (
    PromptCreateRequest,
    PromptListResponse,
    PromptSummary,
)
from app.utils.api_errors import build_response, raise_api_error, with_message
from app.utils.logger import get_logger
from app.utils.prompt_loader import PromptNotFoundError, _prompts_dir, load_prompt

logger = get_logger(__name__)

router = APIRouter(tags=["prompts"])


def _rows_to_summaries(rows: list[Dict[str, Any]]) -> list[PromptSummary]:
    summaries: list[PromptSummary] = []
    for row in rows:
        summaries.append(
            PromptSummary(
                message="",
                id=UUID(str(row["id"])),
                name=row["name"],
                version=int(row.get("version") or 1),
                is_active=bool(row.get("is_active")),
                tenant_id=UUID(str(row["tenant_id"])) if row.get("tenant_id") else None,
                metadata=row.get("metadata") or {},
                source="database",
                created_at=row.get("created_at"),
                system_prompt=row.get("system_prompt"),
                user_prompt_template=row.get("user_prompt_template"),
            )
        )
    return summaries


def _yaml_prompt_summaries(existing_names: set[str]) -> list[PromptSummary]:
    """Enumerate YAML-sourced prompt defaults not already covered by DB rows.

    YAML prompts have no DB id, so we expose them with ``id=None`` and
    ``source="yaml"``. Resolution at query time still prefers DB overrides
    (see :func:`app.utils.prompt_loader.load_prompt`), so surfacing these is
    purely for the frontend dropdown to know the defaults exist.
    """
    summaries: list[PromptSummary] = []
    prompts_dir = _prompts_dir()
    if not prompts_dir.exists():
        return summaries
    for path in sorted(prompts_dir.glob("*.yaml")):
        name = path.stem
        if name in existing_names:
            continue
        try:
            # Passing client=None forces the YAML branch, which also resolves
            # ``${setting}`` placeholders (model / temperature / max_tokens)
            # against runtime config — otherwise the UI shows the literal
            # "${generation_model}" string.
            data = load_prompt(name)
        except PromptNotFoundError:
            continue
        summaries.append(
            PromptSummary(
                message="",
                id=None,
                name=data.get("name", name),
                version=int(data.get("version") or 1),
                is_active=True,
                tenant_id=None,
                metadata=data.get("metadata") or {},
                source="yaml",
                created_at=None,
                system_prompt=data.get("system_prompt"),
                user_prompt_template=data.get("user_prompt_template"),
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
        raise_api_error(500, "prompts.list_failed")

    db_summaries = _rows_to_summaries(list(tenant_rows) + list(global_rows or []))
    existing_names = {s.name for s in db_summaries}
    yaml_summaries = _yaml_prompt_summaries(existing_names)
    return build_response(
        PromptListResponse,
        "prompts.listed",
        prompts=db_summaries + yaml_summaries,
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
        raise_api_error(500, "prompts.create_failed")

    rows = response.data or []
    if not rows:
        raise_api_error(500, "prompts.insert_empty")
    return with_message(_rows_to_summaries(rows)[0], "prompts.created")
