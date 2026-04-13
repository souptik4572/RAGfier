from __future__ import annotations

import json
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import QueryRequest
from app.pipeline.citation_resolver import resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["query"])


@router.post("/query/stream")
async def query_stream(
    payload: QueryRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> EventSourceResponse:
    client = get_service_client()
    try:
        prepared = await prepare_query(
            query=payload.query,
            tenant_id=auth.tenant_id,
            match_count=payload.match_count,
            rerank=payload.rerank,
            prompt_name=payload.prompt_name,
            client=client,
        )
    except QueryPipelineError as exc:
        logger.error("query_stream.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    async def event_generator() -> AsyncIterator[dict]:
        # Emit sources first so the client can pre-render citation cards.
        upfront_citations = (
            resolve_citations("", prepared.final_chunks, include_uncited=True)
            if payload.include_sources
            else []
        )
        yield {
            "event": "sources",
            "data": json.dumps(
                {"citations": [c.model_dump(mode="json") for c in upfront_citations]}
            ),
        }

        if prepared.declined:
            stamp_total_latency(prepared)
            yield {"event": "token", "data": INSUFFICIENT_CONTEXT_MESSAGE}
            yield {
                "event": "done",
                "data": json.dumps(
                    {
                        "retrieval_metadata": prepared.retrieval_metadata.model_dump(mode="json"),
                        "declined": True,
                    }
                ),
            }
            return

        try:
            generator = Generator()
            gen_start = time.perf_counter()
            async for token in generator.stream(
                prompt=prepared.prompt,
                context=prepared.context,
                query=payload.query,
            ):
                yield {"event": "token", "data": token}
        except GenerationError as exc:
            logger.error(
                "query_stream.generation_failed",
                tenant_id=auth.tenant_id,
                error=str(exc),
            )
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}
            return

        prepared.retrieval_metadata.latency_ms.generation = int(
            (time.perf_counter() - gen_start) * 1000
        )
        stamp_total_latency(prepared)
        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "retrieval_metadata": prepared.retrieval_metadata.model_dump(mode="json"),
                    "declined": False,
                }
            ),
        }

    return EventSourceResponse(event_generator())
