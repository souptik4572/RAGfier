from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import HybridQueryResponse, QueryRequest
from app.pipeline.citation_resolver import resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)
from app.utils.api_errors import build_response, raise_api_error
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["query"])


@router.post("/query", response_model=HybridQueryResponse)
async def query_documents(
    payload: QueryRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> HybridQueryResponse:
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
        logger.error("query.pipeline_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise_api_error(500, "query.pipeline_failed", detail=str(exc))

    if prepared.declined:
        stamp_total_latency(prepared)
        logger.info(
            "query.declined",
            tenant_id=auth.tenant_id,
            reason=prepared.decline_reason,
        )
        return build_response(
            HybridQueryResponse,
            "query.declined",
            query=payload.query,
            answer=INSUFFICIENT_CONTEXT_MESSAGE,
            citations=[],
            retrieval_metadata=prepared.retrieval_metadata,
            declined=True,
        )

    try:
        generator = Generator()
        gen_start = time.perf_counter()
        answer = await generator.generate(
            prompt=prepared.prompt,
            context=prepared.context,
            query=payload.query,
        )
    except GenerationError as exc:
        logger.error("query.generation_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise_api_error(500, "query.generation_failed")

    prepared.retrieval_metadata.latency_ms.generation = int(
        (time.perf_counter() - gen_start) * 1000
    )
    stamp_total_latency(prepared)

    citations = (
        resolve_citations(answer, prepared.final_chunks)
        if payload.include_sources
        else []
    )

    logger.info(
        "query.completed",
        tenant_id=auth.tenant_id,
        match_count=payload.match_count,
        cited=len(citations),
        total_ms=prepared.retrieval_metadata.latency_ms.total,
    )
    return build_response(
        HybridQueryResponse,
        "query.completed",
        query=payload.query,
        answer=answer,
        citations=citations,
        retrieval_metadata=prepared.retrieval_metadata,
        declined=False,
    )
