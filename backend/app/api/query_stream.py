from __future__ import annotations

import json
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import QueryRequest
from app.pipeline.citation_resolver import CitationStreamStripper, resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.api_errors import success_payload
from app.utils.integration_resolver import resolve_integration
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["query"])


@router.post("/query/stream")
async def query_stream(
    payload: QueryRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> EventSourceResponse:
    client = get_service_client()
    integration_id_str = str(payload.integration_id) if payload.integration_id else None

    async def event_generator() -> AsyncIterator[dict]:
        try:
            integration = resolve_integration(client, auth.tenant_id, integration_id_str)
            resolved_integration_id = str(integration["id"])
        except HTTPException as exc:
            logger.error(
                "query_stream.integration_resolution_failed",
                tenant_id=auth.tenant_id,
                error=str(exc.detail),
            )
            yield {
                "event": "error",
                "data": json.dumps({"message": "Integration resolution failed", "detail": exc.detail}),
            }
            yield {
                "event": "done",
                "data": json.dumps(success_payload("query.stream_generation_failed", declined=False)),
            }
            return

        try:
            prepared = await prepare_query(
                query=payload.query,
                tenant_id=auth.tenant_id,
                integration_id=resolved_integration_id,
                match_count=payload.match_count,
                rerank=payload.rerank,
                prompt_name=payload.prompt_name,
                client=client,
            )
        except QueryPipelineError as exc:
            logger.error("query_stream.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
            yield {
                "event": "error",
                "data": json.dumps({"message": "Query pipeline failed", "detail": str(exc)}),
            }
            yield {
                "event": "done",
                "data": json.dumps(success_payload("query.stream_generation_failed", declined=False)),
            }
            return
        except Exception as exc:  # defensive: surface to client instead of hanging
            logger.exception(
                "query_stream.unexpected_failure",
                tenant_id=auth.tenant_id,
                error=str(exc),
            )
            yield {
                "event": "error",
                "data": json.dumps({"message": "Unexpected error", "detail": str(exc)}),
            }
            yield {
                "event": "done",
                "data": json.dumps(success_payload("query.stream_generation_failed", declined=False)),
            }
            return

        upfront_citations = (
            resolve_citations("", prepared.final_chunks, include_uncited=True)
            if payload.include_sources
            else []
        )
        yield {
            "event": "sources",
            "data": json.dumps(
                success_payload(
                    "query.sources_prepared",
                    citations=[c.model_dump(mode="json") for c in upfront_citations],
                )
            ),
        }

        if prepared.declined:
            stamp_total_latency(prepared)
            yield {"event": "token", "data": INSUFFICIENT_CONTEXT_MESSAGE}
            yield {
                "event": "done",
                "data": json.dumps(
                    success_payload(
                        "query.stream_declined",
                        retrieval_metadata=prepared.retrieval_metadata.model_dump(mode="json"),
                        declined=True,
                    )
                ),
            }
            return

        gen_start = time.perf_counter()
        stripper = CitationStreamStripper() if not payload.include_sources else None
        try:
            generator = Generator()
            async for token in generator.stream(
                prompt=prepared.prompt,
                context=prepared.context,
                query=payload.query,
                include_citations=payload.include_sources,
            ):
                if stripper is not None:
                    token = stripper.feed(token)
                if token:
                    yield {"event": "token", "data": token}
        except GenerationError as exc:
            if stripper is not None:
                remainder = stripper.flush()
                if remainder:
                    yield {"event": "token", "data": remainder}
            logger.error(
                "query_stream.generation_failed",
                tenant_id=auth.tenant_id,
                error=str(exc),
            )
            yield {
                "event": "error",
                "data": json.dumps({"message": "Generation failed", "detail": str(exc)}),
            }
            yield {
                "event": "done",
                "data": json.dumps(success_payload("query.stream_generation_failed", declined=False)),
            }
            return

        if stripper is not None:
            remainder = stripper.flush()
            if remainder:
                yield {"event": "token", "data": remainder}

        prepared.retrieval_metadata.latency_ms.generation = int(
            (time.perf_counter() - gen_start) * 1000
        )
        stamp_total_latency(prepared)
        yield {
            "event": "done",
            "data": json.dumps(
                success_payload(
                    "query.stream_completed",
                    retrieval_metadata=prepared.retrieval_metadata.model_dump(mode="json"),
                    declined=False,
                )
            ),
        }

    return EventSourceResponse(event_generator())
