from __future__ import annotations

import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from app.api.auth import AuthContext, get_auth_context
from app.api.platform_auth import PlatformAuthContext, require_platform_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    DocumentListResponse,
    DocumentSummary,
    IntegrationQueryRequest,
    IntegrationQueryResponse,
    IngestResponse,
    RetrievalMetadata,
    UsageMetadata,
)
from app.pipeline.citation_resolver import resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.api_errors import build_response, raise_api_error, success_payload
from app.utils.integration_resolver import resolve_integration
from app.utils.logger import get_logger
from app.utils.platform_observability import write_audit_log_async, write_request_log_async
from app.utils.token_counter import count_tokens

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

    suffix = Path(file.filename).suffix.lower().lstrip(".")
    if suffix not in settings.allowed_file_types:
        raise_api_error(422, "ingest.unsupported_file_type", detail={"file_type": suffix})

    contents = await file.read()
    if not contents:
        raise_api_error(422, "ingest.empty_file")
    if len(contents) > settings.max_file_size_bytes:
        raise_api_error(413, "ingest.file_too_large", detail={"max_file_size_mb": settings.max_file_size_mb})

    job_id = str(uuid.uuid4())
    storage_path = f"{auth.tenant_id}/{resolved_integration_id}/{job_id}/{file.filename}"
    try:
        client.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        logger.warning("integrations.upload.storage_failed", tenant_id=auth.tenant_id, job_id=job_id, error=str(exc))
        storage_path = f"local://{file.filename}"

    tmp_dir = Path(tempfile.gettempdir()) / "ragfier" / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / file.filename
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
        file_name=file.filename,
        file_type=suffix,
        document_title=document_title,
    )

    logger.info(
        "integrations.document_uploaded",
        tenant_id=auth.tenant_id,
        integration_id=resolved_integration_id,
        job_id=job_id,
        file_name=file.filename,
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

    started = time.perf_counter()
    client = get_service_client()
    request_id = uuid.uuid4()
    query_token_count = count_tokens(payload.query)

    try:
        prepared = await prepare_query(
            query=payload.query,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            match_count=payload.match_count,
            rerank=payload.rerank,
            prompt_name=payload.prompt_name,
            client=client,
        )
    except QueryPipelineError as exc:
        logger.error("integrations.query.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=f"/v1/integrations/{integration_id}/query",
            method="POST",
            status_code=500,
            latency_ms=_elapsed_ms(started),
            input_tokens=query_token_count,
            error_code="pipeline_failed",
        )
        raise_api_error(500, "query.pipeline_failed", detail=str(exc))

    if prepared.declined:
        stamp_total_latency(prepared)
        usage = UsageMetadata(input_tokens=query_token_count)
        usage.total_tokens = usage.input_tokens
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=f"/v1/integrations/{integration_id}/query",
            method="POST",
            status_code=200,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            input_tokens=usage.input_tokens,
            output_tokens=0,
            metadata={"declined": True},
        )
        return build_response(
            IntegrationQueryResponse,
            "query.declined",
            request_id=request_id,
            query=payload.query,
            answer=INSUFFICIENT_CONTEXT_MESSAGE,
            citations=[],
            retrieval_metadata=prepared.retrieval_metadata,
            declined=True,
            usage=usage.model_dump(mode="json"),
        )

    try:
        generator = Generator()
        gen_started = time.perf_counter()
        answer = await generator.generate(
            prompt=prepared.prompt,
            context=prepared.context,
            query=payload.query,
        )
    except GenerationError as exc:
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=f"/v1/integrations/{integration_id}/query",
            method="POST",
            status_code=500,
            latency_ms=_elapsed_ms(started),
            input_tokens=query_token_count,
            error_code="generation_failed",
        )
        raise_api_error(500, "query.generation_failed", detail=str(exc))

    prepared.retrieval_metadata.latency_ms.generation = _elapsed_ms(gen_started)
    stamp_total_latency(prepared)
    citations = resolve_citations(answer, prepared.final_chunks) if payload.include_sources else []
    usage = _usage_from_texts_cached(query_token_count, answer)
    await write_request_log_async(
        client,
        tenant_id=auth.tenant_id,
        integration_id=auth.integration_id,
        api_key_id=auth.api_key_id,
        endpoint=f"/v1/integrations/{integration_id}/query",
        method="POST",
        status_code=200,
        latency_ms=prepared.retrieval_metadata.latency_ms.total,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        metadata={
            "external_user_id": payload.external_user_id,
            "session_id": payload.session_id,
            "tags": payload.tags,
        },
    )
    return build_response(
        IntegrationQueryResponse,
        "query.completed",
        request_id=request_id,
        query=payload.query,
        answer=answer,
        citations=citations,
        retrieval_metadata=prepared.retrieval_metadata,
        declined=False,
        usage=usage.model_dump(mode="json"),
    )


@router.post("/{integration_id}/query/stream")
async def query_integration_stream(
    integration_id: UUID,
    payload: IntegrationQueryRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("query:read")),
) -> EventSourceResponse:
    if str(integration_id) != auth.integration_id:
        raise_api_error(403, "platform_auth.integration_mismatch")

    client = get_service_client()
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    query_token_count = count_tokens(payload.query)

    try:
        prepared = await prepare_query(
            query=payload.query,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            match_count=payload.match_count,
            rerank=payload.rerank,
            prompt_name=payload.prompt_name,
            client=client,
        )
    except QueryPipelineError as exc:
        raise_api_error(500, "query.pipeline_failed", detail=str(exc))

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        citations = (
            resolve_citations("", prepared.final_chunks, include_uncited=True)
            if payload.include_sources
            else []
        )
        yield {
            "event": "sources",
            "data": json.dumps(
                success_payload(
                    "query.sources_prepared",
                    request_id=request_id,
                    citations=[c.model_dump(mode="json") for c in citations],
                )
            ),
        }

        if prepared.declined:
            stamp_total_latency(prepared)
            await write_request_log_async(
                client,
                tenant_id=auth.tenant_id,
                integration_id=auth.integration_id,
                api_key_id=auth.api_key_id,
                endpoint=f"/v1/integrations/{integration_id}/query/stream",
                method="POST",
                status_code=200,
                latency_ms=prepared.retrieval_metadata.latency_ms.total,
                input_tokens=query_token_count,
                metadata={"declined": True},
            )
            yield {"event": "token", "data": INSUFFICIENT_CONTEXT_MESSAGE}
            yield {
                "event": "done",
                "data": json.dumps(
                    success_payload(
                        "query.stream_declined",
                        request_id=request_id,
                        declined=True,
                        retrieval_metadata=prepared.retrieval_metadata.model_dump(mode="json"),
                        usage=_usage_from_texts_cached(query_token_count, "").model_dump(mode="json"),
                    )
                ),
            }
            return

        answer_parts: list[str] = []
        try:
            generator = Generator()
            gen_started = time.perf_counter()
            async for token in generator.stream(
                prompt=prepared.prompt,
                context=prepared.context,
                query=payload.query,
            ):
                answer_parts.append(token)
                yield {"event": "token", "data": token}
        except GenerationError as exc:
            yield {
                "event": "error",
                "data": json.dumps(success_payload("query.stream_generation_failed", detail=str(exc))),
            }
            return

        prepared.retrieval_metadata.latency_ms.generation = _elapsed_ms(gen_started)
        stamp_total_latency(prepared)
        answer = "".join(answer_parts)
        usage = _usage_from_texts_cached(query_token_count, answer)
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=f"/v1/integrations/{integration_id}/query/stream",
            method="POST",
            status_code=200,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        yield {
            "event": "done",
            "data": json.dumps(
                success_payload(
                    "query.stream_completed",
                    request_id=request_id,
                    declined=False,
                    retrieval_metadata=prepared.retrieval_metadata.model_dump(mode="json"),
                    usage=usage.model_dump(mode="json"),
                )
            ),
        }

    return EventSourceResponse(event_generator())


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _usage_from_texts_cached(query_tokens: int, answer: str) -> UsageMetadata:
    usage = UsageMetadata(
        input_tokens=query_tokens,
        output_tokens=count_tokens(answer) if answer else 0,
    )
    usage.total_tokens = usage.input_tokens + usage.output_tokens
    usage.estimated_cost_usd = round((usage.total_tokens / 1000) * 0.0002, 6)
    return usage
