"""Shared helpers for query/stream API endpoints.

The platform, integration-flat, and integration-scoped query routes all
follow the same recipe (prepare → generate → log), differing only in the
response model, the ``endpoint`` string that gets recorded, the log
prefix used when the pipeline raises, and whether the handler should
write an audit-log entry. Before this module the same ~140 lines were
duplicated four times — once per variant — which made every small
observability tweak a four-way edit.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import Response
from sse_starlette.sse import EventSourceResponse

from app.api.rate_limit import (
    enforce_api_key_query_limit,
    enforce_api_key_stream_limits,
    release_stream_limit_lease,
)
from app.models.schemas import UsageMetadata
from app.pipeline.citation_resolver import (
    CitationStreamStripper,
    resolve_citations,
    strip_citation_markers,
)
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.api_errors import build_response, raise_api_error, success_payload
from app.utils.logger import get_logger
from app.utils.platform_observability import (
    write_audit_log_async,
    write_request_log_async,
)
from app.utils.token_counter import count_tokens

logger = get_logger(__name__)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def usage_from_counts(query_tokens: int, answer: str) -> UsageMetadata:
    """Build UsageMetadata reusing a precomputed input-token count.

    The input count comes from the caller because tiktoken encoding is
    not free and the value was previously recomputed on every branch
    (pipeline-error, decline, generation-error, success) of each query
    handler.
    """
    usage = UsageMetadata(
        input_tokens=query_tokens,
        output_tokens=count_tokens(answer) if answer else 0,
    )
    usage.total_tokens = usage.input_tokens + usage.output_tokens
    usage.estimated_cost_usd = round((usage.total_tokens / 1000) * 0.0002, 6)
    return usage


async def execute_query(
    *,
    payload: Any,
    auth: Any,
    client: Any,
    response_model: type,
    endpoint: str,
    log_prefix: str,
    write_audit: bool = False,
    response: Response | None = None,
) -> Any:
    """Run the full non-streaming query flow shared by three endpoints."""
    rate_limit_headers = await enforce_api_key_query_limit(auth)
    if response is not None:
        response.headers.update(rate_limit_headers)
    started = time.perf_counter()
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
        logger.error(f"{log_prefix}.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=endpoint,
            method="POST",
            status_code=500,
            latency_ms=elapsed_ms(started),
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
            endpoint=endpoint,
            method="POST",
            status_code=200,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            input_tokens=usage.input_tokens,
            output_tokens=0,
            metadata={"declined": True},
        )
        if write_audit:
            await write_audit_log_async(
                client,
                tenant_id=auth.tenant_id,
                actor_type="api_key",
                actor_id=auth.api_key_id,
                action="query.executed",
                resource_type="query",
                resource_id=str(request_id),
                metadata={"declined": True},
            )
        return build_response(
            response_model,
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
            include_citations=payload.include_sources,
        )
    except GenerationError as exc:
        await write_request_log_async(
            client,
            tenant_id=auth.tenant_id,
            integration_id=auth.integration_id,
            api_key_id=auth.api_key_id,
            endpoint=endpoint,
            method="POST",
            status_code=500,
            latency_ms=elapsed_ms(started),
            input_tokens=query_token_count,
            error_code="generation_failed",
        )
        raise_api_error(500, "query.generation_failed", detail=str(exc))

    prepared.retrieval_metadata.latency_ms.generation = elapsed_ms(gen_started)
    stamp_total_latency(prepared)
    if payload.include_sources:
        citations = resolve_citations(answer, prepared.final_chunks)
    else:
        citations = []
        answer = strip_citation_markers(answer)
    usage = usage_from_counts(query_token_count, answer)
    await write_request_log_async(
        client,
        tenant_id=auth.tenant_id,
        integration_id=auth.integration_id,
        api_key_id=auth.api_key_id,
        endpoint=endpoint,
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
    if write_audit:
        await write_audit_log_async(
            client,
            tenant_id=auth.tenant_id,
            actor_type="api_key",
            actor_id=auth.api_key_id,
            action="query.executed",
            resource_type="query",
            resource_id=str(request_id),
            metadata={},
        )
    return build_response(
        response_model,
        "query.completed",
        request_id=request_id,
        query=payload.query,
        answer=answer,
        citations=citations,
        retrieval_metadata=prepared.retrieval_metadata,
        declined=False,
        usage=usage.model_dump(mode="json"),
    )


async def build_stream_response(
    *,
    payload: Any,
    auth: Any,
    client: Any,
    endpoint: str,
) -> EventSourceResponse:
    """Prepare the query and return an SSE response for the three stream routes."""
    stream_lease, rate_limit_headers = await enforce_api_key_stream_limits(auth)
    request_id = str(uuid.uuid4())
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
        try:
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
                    endpoint=endpoint,
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
                            usage=usage_from_counts(query_token_count, "").model_dump(mode="json"),
                        )
                    ),
                }
                return

            answer_parts: list[str] = []
            stripper = CitationStreamStripper() if not payload.include_sources else None
            try:
                generator = Generator()
                gen_started = time.perf_counter()
                async for token in generator.stream(
                    prompt=prepared.prompt,
                    context=prepared.context,
                    query=payload.query,
                    include_citations=payload.include_sources,
                ):
                    answer_parts.append(token)
                    if stripper is not None:
                        token = stripper.feed(token)
                    if token:
                        yield {"event": "token", "data": token}
            except GenerationError as exc:
                if stripper is not None:
                    remainder = stripper.flush()
                    if remainder:
                        yield {"event": "token", "data": remainder}
                yield {
                    "event": "error",
                    "data": json.dumps(success_payload("query.stream_generation_failed", detail=str(exc))),
                }
                return

            if stripper is not None:
                remainder = stripper.flush()
                if remainder:
                    yield {"event": "token", "data": remainder}

            prepared.retrieval_metadata.latency_ms.generation = elapsed_ms(gen_started)
            stamp_total_latency(prepared)
            answer = "".join(answer_parts)
            usage = usage_from_counts(query_token_count, answer)
            await write_request_log_async(
                client,
                tenant_id=auth.tenant_id,
                integration_id=auth.integration_id,
                api_key_id=auth.api_key_id,
                endpoint=endpoint,
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
        finally:
            await release_stream_limit_lease(stream_lease)

    return EventSourceResponse(event_generator(), headers=rate_limit_headers)
