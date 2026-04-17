from __future__ import annotations

import json
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status
from sse_starlette.sse import EventSourceResponse

from app.api.auth import _slugify
from app.api.platform_auth import PlatformAuthContext, require_platform_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    AuditLogEntry,
    AuditLogListResponse,
    ConnectorCreateRequest,
    ConnectorSummary,
    ConnectorSyncResponse,
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentSummary,
    JobStatusResponse,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseSummary,
    QueryRequestV1,
    QueryResponseV1,
    UploadDocumentResponse,
    UsageBucket,
    UsageMetadata,
    UsageResponse,
)
from app.pipeline.citation_resolver import resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.orchestrator import run_pipeline_task
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.api_errors import build_response, raise_api_error, success_payload
from app.utils.logger import get_logger
from app.utils.platform_observability import (
    write_audit_log,
    write_audit_log_async,
    write_request_log_async,
)
from app.utils.platform_security import encrypt_connector_config
from app.utils.token_counter import count_tokens

logger = get_logger(__name__)

router = APIRouter(prefix="/v1", tags=["platform-v1"])


@router.post("/knowledge-bases", response_model=KnowledgeBaseSummary, status_code=201)
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("kb:write")),
) -> KnowledgeBaseSummary:
    client = get_service_client()
    slug = payload.slug or _slugify(payload.name)
    row = _insert_row(
        client,
        "knowledge_bases",
        {
            "tenant_id": auth.tenant_id,
            "name": payload.name,
            "slug": slug,
            "description": payload.description,
            "status": "active",
            "settings": payload.settings,
        },
        "platform.knowledge_base_created",
    )
    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="knowledge_base.created",
        resource_type="knowledge_base",
        resource_id=str(row["id"]),
        metadata={"integration_id": auth.integration_id},
    )
    return _kb_summary(row, "platform.knowledge_base_created")


@router.get("/knowledge-bases", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    auth: PlatformAuthContext = Depends(require_platform_context("kb:read")),
) -> KnowledgeBaseListResponse:
    client = get_service_client()
    rows = _select_rows(client, "knowledge_bases", tenant_id=auth.tenant_id)
    return build_response(
        KnowledgeBaseListResponse,
        "platform.knowledge_bases_listed",
        knowledge_bases=[_kb_summary(row).model_dump(mode="json") for row in rows],
    )


@router.post("/documents/upload", response_model=UploadDocumentResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document_v1(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    knowledge_base_id: UUID = Form(...),
    document_title: Optional[str] = Form(default=None),
    auth: PlatformAuthContext = Depends(require_platform_context("documents:write")),
) -> UploadDocumentResponse:
    started = time.perf_counter()
    client = get_service_client()
    _require_kb(client, auth.tenant_id, str(knowledge_base_id))
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
    storage_path = f"{auth.tenant_id}/{knowledge_base_id}/{job_id}/{file.filename}"
    try:
        client.storage.from_(settings.supabase_storage_bucket).upload(
            path=storage_path,
            file=contents,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        logger.warning("platform.upload.storage_failed", tenant_id=auth.tenant_id, job_id=job_id, error=str(exc))
        storage_path = f"local://{file.filename}"

    tmp_dir = Path(tempfile.gettempdir()) / "ragfier" / job_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = tmp_dir / file.filename
    tmp_file.write_bytes(contents)

    client.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": auth.tenant_id,
            "knowledge_base_id": str(knowledge_base_id),
            "file_name": file.filename,
            "file_path": storage_path,
            "status": "pending",
            "source_type": "upload",
            "metadata": {"document_title": document_title} if document_title else {},
        }
    ).execute()

    background_tasks.add_task(
        run_pipeline_task,
        job_id=job_id,
        tenant_id=auth.tenant_id,
        knowledge_base_id=str(knowledge_base_id),
        source_type="upload",
        file_path=str(tmp_file),
        file_name=file.filename,
        file_type=suffix,
        document_title=document_title,
    )

    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="document.uploaded",
        resource_type="document",
        resource_id=job_id,
        metadata={"knowledge_base_id": str(knowledge_base_id), "file_name": file.filename},
    )
    await write_request_log_async(
        client,
        tenant_id=auth.tenant_id,
        integration_id=auth.integration_id,
        api_key_id=auth.api_key_id,
        endpoint="/v1/documents/upload",
        method="POST",
        status_code=202,
        latency_ms=_elapsed_ms(started),
        input_tokens=0,
        output_tokens=0,
        metadata={"knowledge_base_id": str(knowledge_base_id)},
    )
    return build_response(
        UploadDocumentResponse,
        "platform.document_uploaded",
        job_id=UUID(job_id),
        status="pending",
        knowledge_base_id=knowledge_base_id,
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    auth: PlatformAuthContext = Depends(require_platform_context("documents:read")),
) -> DocumentListResponse:
    client = get_service_client()
    rows = _select_rows(client, "ingestion_jobs", tenant_id=auth.tenant_id)
    docs = [
        _document_summary(row).model_dump(mode="json")
        for row in rows
        if row.get("status") != "deleted"
    ]
    return build_response(DocumentListResponse, "platform.documents_listed", documents=docs)


@router.get("/documents/{document_id}", response_model=DocumentSummary)
async def get_document(
    document_id: UUID,
    auth: PlatformAuthContext = Depends(require_platform_context("documents:read")),
) -> DocumentSummary:
    client = get_service_client()
    row = _get_ingestion_job(client, auth.tenant_id, str(document_id))
    if row is None or row.get("status") == "deleted":
        raise_api_error(404, "platform.document_not_found")
    return _document_summary(row, "platform.documents_listed")


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: UUID,
    auth: PlatformAuthContext = Depends(require_platform_context("documents:write")),
) -> DocumentDeleteResponse:
    client = get_service_client()
    row = _get_ingestion_job(client, auth.tenant_id, str(document_id))
    if row is None:
        raise_api_error(404, "platform.document_not_found")

    deleted = _delete_rows(client, "documents", "job_id", str(document_id))
    client.table("ingestion_jobs").update({"status": "deleted"}).eq("id", str(document_id)).execute()
    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="document.deleted",
        resource_type="document",
        resource_id=str(document_id),
        metadata={"deleted_chunks": deleted},
    )
    return build_response(
        DocumentDeleteResponse,
        "platform.document_deleted",
        document_id=str(document_id),
        deleted_chunks=deleted,
    )


@router.post("/query", response_model=QueryResponseV1)
async def query_v1(
    payload: QueryRequestV1,
    auth: PlatformAuthContext = Depends(require_platform_context("query:read")),
) -> QueryResponseV1:
    started = time.perf_counter()
    client = get_service_client()
    _require_kbs(client, auth.tenant_id, payload.knowledge_base_ids)
    request_id = uuid.uuid4()
    # Compute once — tiktoken encoding is not free, and this value was
    # previously recomputed on every success/declined/error branch below.
    query_token_count = count_tokens(payload.query)

    try:
        prepared = await prepare_query(
            query=payload.query,
            tenant_id=auth.tenant_id,
            knowledge_base_ids=[str(kb_id) for kb_id in payload.knowledge_base_ids],
            match_count=payload.match_count,
            rerank=payload.rerank,
            prompt_name=payload.prompt_name,
            client=client,
        )
    except QueryPipelineError as exc:
        logger.error("platform.query.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint="/v1/query",
            method="POST",
            status_code=500,
            latency_ms=_elapsed_ms(started),
            input_tokens=query_token_count,
            error_code="pipeline_failed",
            metadata={"knowledge_base_ids": [str(kb_id) for kb_id in payload.knowledge_base_ids]},
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
            endpoint="/v1/query",
            method="POST",
            status_code=200,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            input_tokens=usage.input_tokens,
            output_tokens=0,
            metadata={"declined": True},
        )
        await write_audit_log_async(
            client,
            tenant_id=auth.tenant_id,
            actor_type="api_key",
            actor_id=auth.api_key_id,
            action="query.executed",
            resource_type="query",
            resource_id=str(request_id),
            metadata={"declined": True, "knowledge_base_ids": [str(kb_id) for kb_id in payload.knowledge_base_ids]},
        )
        return build_response(
            QueryResponseV1,
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
            endpoint="/v1/query",
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
        endpoint="/v1/query",
        method="POST",
        status_code=200,
        latency_ms=prepared.retrieval_metadata.latency_ms.total,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        metadata={
            "knowledge_base_ids": [str(kb_id) for kb_id in payload.knowledge_base_ids],
            "external_user_id": payload.external_user_id,
            "session_id": payload.session_id,
            "tags": payload.tags,
        },
    )
    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="query.executed",
        resource_type="query",
        resource_id=str(request_id),
        metadata={"knowledge_base_ids": [str(kb_id) for kb_id in payload.knowledge_base_ids]},
    )
    return build_response(
        QueryResponseV1,
        "query.completed",
        request_id=request_id,
        query=payload.query,
        answer=answer,
        citations=citations,
        retrieval_metadata=prepared.retrieval_metadata,
        declined=False,
        usage=usage.model_dump(mode="json"),
    )


@router.post("/query/stream")
async def query_stream_v1(
    payload: QueryRequestV1,
    auth: PlatformAuthContext = Depends(require_platform_context("query:read")),
) -> EventSourceResponse:
    client = get_service_client()
    _require_kbs(client, auth.tenant_id, payload.knowledge_base_ids)
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    query_token_count = count_tokens(payload.query)

    try:
        prepared = await prepare_query(
            query=payload.query,
            tenant_id=auth.tenant_id,
            knowledge_base_ids=[str(kb_id) for kb_id in payload.knowledge_base_ids],
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
                endpoint="/v1/query/stream",
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
            endpoint="/v1/query/stream",
            method="POST",
            status_code=200,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            metadata={"knowledge_base_ids": [str(kb_id) for kb_id in payload.knowledge_base_ids]},
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


@router.post("/connectors/s3", response_model=ConnectorSummary, status_code=201)
async def create_s3_connector(
    payload: ConnectorCreateRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("connectors:write")),
) -> ConnectorSummary:
    return _create_connector("s3", payload, auth)


@router.post("/connectors/supabase", response_model=ConnectorSummary, status_code=201)
async def create_supabase_connector(
    payload: ConnectorCreateRequest,
    auth: PlatformAuthContext = Depends(require_platform_context("connectors:write")),
) -> ConnectorSummary:
    return _create_connector("supabase", payload, auth)


@router.post("/connectors/{connector_id}/sync", response_model=ConnectorSyncResponse, status_code=202)
async def trigger_connector_sync(
    connector_id: UUID,
    auth: PlatformAuthContext = Depends(require_platform_context("connectors:write")),
) -> ConnectorSyncResponse:
    client = get_service_client()
    connector = _get_row(client, "connector_sources", "id", str(connector_id), tenant_id=auth.tenant_id)
    if connector is None:
        raise_api_error(404, "platform.connector_not_found")

    row = _insert_row(
        client,
        "connector_sync_jobs",
        {
            "tenant_id": auth.tenant_id,
            "connector_source_id": str(connector_id),
            "knowledge_base_id": connector["knowledge_base_id"],
            "status": "pending",
            "trigger": "manual",
            "metadata": {"connector_type": connector["type"]},
        },
        "platform.connector_sync_started",
    )
    await write_audit_log_async(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="connector.sync_triggered",
        resource_type="connector",
        resource_id=str(connector_id),
        metadata={"sync_job_id": str(row["id"])},
    )
    return build_response(
        ConnectorSyncResponse,
        "platform.connector_sync_started",
        sync_job_id=UUID(str(row["id"])),
        status=str(row["status"]),
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_v1(
    job_id: UUID,
    auth: PlatformAuthContext = Depends(require_platform_context("documents:read")),
) -> JobStatusResponse:
    client = get_service_client()
    row = _get_ingestion_job(client, auth.tenant_id, str(job_id))
    if row is None:
        raise_api_error(404, "status.job_not_found", detail={"job_id": str(job_id)})
    return build_response(
        JobStatusResponse,
        "platform.job_fetched",
        job_id=job_id,
        status=row["status"],
        file_name=row["file_name"],
        total_chunks=row.get("total_chunks") or 0,
        processed_chunks=row.get("processed_chunks") or 0,
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        updated_at=row.get("updated_at") or row["created_at"],
    )


@router.get("/usage", response_model=UsageResponse)
async def list_usage(
    days: int = Query(default=30, ge=1, le=90),
    auth: PlatformAuthContext = Depends(require_platform_context("analytics:read")),
) -> UsageResponse:
    client = get_service_client()
    # Cap at ~100 rows/day × requested window. Previously pulled the entire
    # request_logs table for the tenant (unbounded) and re-sliced in Python
    # — that is O(total tenant history) per call and will OOM large tenants.
    rows = _select_rows_limited(
        client, "request_logs", tenant_id=auth.tenant_id, limit=days * 100
    )
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "window_start": None,
        "request_count": 0,
        "success_count": 0,
        "error_count": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "latency_total": 0,
    })
    for row in rows:
        key = str(row.get("created_at") or "")[:10]
        bucket = buckets[key]
        bucket["window_start"] = _coerce_datetime(row.get("created_at"))
        bucket["request_count"] += 1
        bucket["success_count"] += 1 if int(row.get("status_code") or 0) < 400 else 0
        bucket["error_count"] += 1 if int(row.get("status_code") or 0) >= 400 else 0
        bucket["total_input_tokens"] += int(row.get("input_tokens") or 0)
        bucket["total_output_tokens"] += int(row.get("output_tokens") or 0)
        bucket["latency_total"] += int(row.get("latency_ms") or 0)

    usage_buckets = []
    for bucket in buckets.values():
        count = bucket["request_count"] or 1
        usage_buckets.append(
            UsageBucket(
                window_start=bucket["window_start"],
                request_count=bucket["request_count"],
                success_count=bucket["success_count"],
                error_count=bucket["error_count"],
                total_input_tokens=bucket["total_input_tokens"],
                total_output_tokens=bucket["total_output_tokens"],
                avg_latency_ms=round(bucket["latency_total"] / count, 2),
            )
        )
    usage_buckets.sort(key=lambda item: item.window_start.isoformat() if item.window_start else "")
    return build_response(
        UsageResponse,
        "platform.usage_listed",
        buckets=[bucket.model_dump(mode="json") for bucket in usage_buckets],
    )


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    auth: PlatformAuthContext = Depends(require_platform_context("analytics:read")),
) -> AuditLogListResponse:
    client = get_service_client()
    rows = _select_rows_limited(
        client, "audit_logs", tenant_id=auth.tenant_id, limit=limit
    )
    logs = [
        AuditLogEntry(
            id=UUID(str(row["id"])),
            tenant_id=UUID(str(row["tenant_id"])),
            actor_type=str(row["actor_type"]),
            actor_id=row.get("actor_id"),
            action=str(row["action"]),
            resource_type=row.get("resource_type"),
            resource_id=row.get("resource_id"),
            metadata=row.get("metadata") or {},
            created_at=row.get("created_at"),
        ).model_dump(mode="json")
        for row in rows
    ]
    return build_response(AuditLogListResponse, "platform.audit_logs_listed", audit_logs=logs)


def _create_connector(
    connector_type: str,
    payload: ConnectorCreateRequest,
    auth: PlatformAuthContext,
) -> ConnectorSummary:
    client = get_service_client()
    _require_kb(client, auth.tenant_id, str(payload.knowledge_base_id))
    config = {
        "bucket": payload.bucket,
        "prefix": payload.prefix,
        "storage_bucket": payload.storage_bucket,
        "path_prefix": payload.path_prefix,
        "metadata": payload.metadata,
    }
    row = _insert_row(
        client,
        "connector_sources",
        {
            "tenant_id": auth.tenant_id,
            "knowledge_base_id": str(payload.knowledge_base_id),
            "type": connector_type,
            "name": payload.name,
            "status": "active",
            "sync_mode": "manual",
            "encrypted_config": encrypt_connector_config(config),
            "config_summary": {k: v for k, v in config.items() if k != "metadata" and v is not None},
            "metadata": payload.metadata,
        },
        "platform.connector_created",
    )
    write_audit_log(
        client,
        tenant_id=auth.tenant_id,
        actor_type="api_key",
        actor_id=auth.api_key_id,
        action="connector.created",
        resource_type="connector",
        resource_id=str(row["id"]),
        metadata={"type": connector_type, "knowledge_base_id": str(payload.knowledge_base_id)},
    )
    return _connector_summary(row, "platform.connector_created")


def _insert_row(client: Any, table: str, payload: dict[str, Any], message_key: str) -> dict[str, Any]:
    try:
        rows = client.table(table).insert(payload).execute().data or []
    except Exception as exc:
        logger.error("platform.insert_failed", table=table, error=str(exc))
        raise_api_error(500, message_key)
    if not rows:
        raise_api_error(500, message_key)
    return rows[0]


def _select_rows(client: Any, table: str, *, tenant_id: str) -> list[dict[str, Any]]:
    try:
        return client.table(table).select("*").eq("tenant_id", tenant_id).execute().data or []
    except Exception as exc:
        logger.error("platform.select_failed", table=table, tenant_id=tenant_id, error=str(exc))
        raise_api_error(500, "common.internal_error")


def _select_rows_limited(
    client: Any, table: str, *, tenant_id: str, limit: int
) -> list[dict[str, Any]]:
    try:
        return (
            client.table(table)
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.error("platform.select_failed", table=table, tenant_id=tenant_id, error=str(exc))
        raise_api_error(500, "common.internal_error")


def _get_row(client: Any, table: str, column: str, value: str, *, tenant_id: str) -> Optional[dict[str, Any]]:
    rows = (
        client.table(table)
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq(column, value)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _get_ingestion_job(client: Any, tenant_id: str, job_id: str) -> Optional[dict[str, Any]]:
    return _get_row(client, "ingestion_jobs", "id", job_id, tenant_id=tenant_id)


def _delete_rows(client: Any, table: str, column: str, value: str) -> int:
    query = client.table(table)
    if hasattr(query, "delete"):
        rows = query.delete().eq(column, value).execute().data or []
        return len(rows)
    matched = query.select("*").eq(column, value).execute().data or []
    remaining = [row for row in client.rows(table) if row.get(column) != value]
    client._tables[table].rows = remaining  # type: ignore[attr-defined]
    return len(matched)


def _require_kb(client: Any, tenant_id: str, knowledge_base_id: str) -> dict[str, Any]:
    row = _get_row(client, "knowledge_bases", "id", knowledge_base_id, tenant_id=tenant_id)
    if row is None:
        raise_api_error(404, "platform.knowledge_base_not_found")
    return row


def _require_kbs(client: Any, tenant_id: str, knowledge_base_ids: Iterable[UUID]) -> None:
    ids = [str(kb_id) for kb_id in knowledge_base_ids]
    if not ids:
        return
    # Previously fetched ALL knowledge_bases for the tenant and scanned in
    # Python — unbounded and slow for large tenants. Filter server-side via
    # `.in_()` so we only pull the rows we need to validate.
    try:
        rows = (
            client.table("knowledge_bases")
            .select("id")
            .eq("tenant_id", tenant_id)
            .in_("id", ids)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.error("platform.require_kbs_failed", tenant_id=tenant_id, error=str(exc))
        raise_api_error(500, "common.internal_error")
    found = {str(row["id"]) for row in rows}
    if not all(kb_id in found for kb_id in ids):
        raise_api_error(404, "platform.knowledge_base_not_found")


def _kb_summary(row: dict[str, Any], message_key: str = "") -> KnowledgeBaseSummary:
    model = KnowledgeBaseSummary(
        message="",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        name=str(row["name"]),
        slug=str(row["slug"]),
        description=row.get("description"),
        status=str(row.get("status") or "active"),
        settings=row.get("settings") or {},
        created_at=row.get("created_at"),
    )
    return model if not message_key else build_response(KnowledgeBaseSummary, message_key, **model.model_dump(mode="json", exclude={"message"}))


def _document_summary(row: dict[str, Any], message_key: str = "") -> DocumentSummary:
    model = DocumentSummary(
        message="",
        id=str(row["id"]),
        tenant_id=UUID(str(row["tenant_id"])),
        knowledge_base_id=UUID(str(row["knowledge_base_id"])) if row.get("knowledge_base_id") else None,
        file_name=str(row["file_name"]),
        document_title=(row.get("metadata") or {}).get("document_title"),
        source_type=row.get("source_type"),
        source_id=UUID(str(row["source_id"])) if row.get("source_id") else None,
        status=str(row.get("status") or "pending"),
        chunk_count=int(row.get("processed_chunks") or 0),
        created_at=row.get("created_at"),
    )
    return model if not message_key else build_response(DocumentSummary, message_key, **model.model_dump(mode="json", exclude={"message"}))


def _connector_summary(row: dict[str, Any], message_key: str = "") -> ConnectorSummary:
    model = ConnectorSummary(
        message="",
        id=UUID(str(row["id"])),
        tenant_id=UUID(str(row["tenant_id"])),
        knowledge_base_id=UUID(str(row["knowledge_base_id"])),
        type=str(row["type"]),
        name=str(row["name"]),
        status=str(row["status"]),
        config_summary=row.get("config_summary") or {},
        sync_mode=str(row.get("sync_mode") or "manual"),
        last_synced_at=row.get("last_synced_at"),
        created_at=row.get("created_at"),
    )
    return model if not message_key else build_response(ConnectorSummary, message_key, **model.model_dump(mode="json", exclude={"message"}))


def _usage_from_texts(query: str, answer: str) -> UsageMetadata:
    return _usage_from_texts_cached(count_tokens(query), answer)


def _usage_from_texts_cached(query_tokens: int, answer: str) -> UsageMetadata:
    """Variant that reuses a precomputed input-token count — callers on the
    query hot path previously recomputed ``count_tokens(query)`` up to four
    times per request (pipeline error, decline, generation error, success)."""
    usage = UsageMetadata(
        input_tokens=query_tokens,
        output_tokens=count_tokens(answer) if answer else 0,
    )
    usage.total_tokens = usage.input_tokens + usage.output_tokens
    usage.estimated_cost_usd = round((usage.total_tokens / 1000) * 0.0002, 6)
    return usage


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    return None
