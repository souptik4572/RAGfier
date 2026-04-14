"""Run the production query pipeline against a golden sample.

This is the thin bridge between the evaluation runner and the live
Phase 2 pipeline. Isolating it here means the runner can be unit tested
by monkey-patching `run_sample_pipeline` without touching Ragas or
Supabase.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.pipeline.citation_resolver import resolve_citations
from app.pipeline.generator import Generator, GenerationError
from app.pipeline.query_pipeline import (
    INSUFFICIENT_CONTEXT_MESSAGE,
    QueryPipelineError,
    prepare_query,
    stamp_total_latency,
)


@dataclass
class SamplePipelineResult:
    query: str
    answer: str
    retrieved_contexts: List[str]
    citations: List[Dict[str, Any]]
    declined: bool
    latency_ms: int
    model: Optional[str]
    prompt_version: Optional[str]
    num_chunks_retrieved: int
    top_rerank_score: Optional[float]


async def run_sample_pipeline(
    *,
    query: str,
    tenant_id: str,
    client: Any,
    match_count: int = 5,
    rerank: bool = True,
    prompt_name: Optional[str] = None,
) -> SamplePipelineResult:
    """Execute the full embed → retrieve → rerank → generate pipeline for one sample."""
    try:
        prepared = await prepare_query(
            query=query,
            tenant_id=tenant_id,
            match_count=match_count,
            rerank=rerank,
            prompt_name=prompt_name,
            client=client,
        )
    except QueryPipelineError as exc:
        raise RuntimeError(f"Query pipeline failed for sample: {exc}") from exc

    if prepared.declined:
        stamp_total_latency(prepared)
        retrieved = [c.get("content", "") for c in prepared.final_chunks]
        return SamplePipelineResult(
            query=query,
            answer=INSUFFICIENT_CONTEXT_MESSAGE,
            retrieved_contexts=retrieved,
            citations=[],
            declined=True,
            latency_ms=prepared.retrieval_metadata.latency_ms.total,
            model=prepared.retrieval_metadata.model,
            prompt_version=prepared.retrieval_metadata.prompt_version,
            num_chunks_retrieved=len(prepared.final_chunks),
            top_rerank_score=_top_rerank_score(prepared.final_chunks),
        )

    generator = Generator()
    gen_start = time.perf_counter()
    try:
        answer = await generator.generate(
            prompt=prepared.prompt,
            context=prepared.context,
            query=query,
        )
    except GenerationError as exc:
        raise RuntimeError(f"Generation failed for sample: {exc}") from exc

    prepared.retrieval_metadata.latency_ms.generation = int(
        (time.perf_counter() - gen_start) * 1000
    )
    stamp_total_latency(prepared)

    citation_models = resolve_citations(answer, prepared.final_chunks)
    citations = [c.model_dump(mode="json") for c in citation_models]
    retrieved_contexts = [c["content"] for c in citations] or [
        c.get("content", "") for c in prepared.final_chunks
    ]

    return SamplePipelineResult(
        query=query,
        answer=answer,
        retrieved_contexts=retrieved_contexts,
        citations=citations,
        declined=False,
        latency_ms=prepared.retrieval_metadata.latency_ms.total,
        model=prepared.retrieval_metadata.model,
        prompt_version=prepared.retrieval_metadata.prompt_version,
        num_chunks_retrieved=len(prepared.final_chunks),
        top_rerank_score=_top_rerank_score(prepared.final_chunks),
    )


def _top_rerank_score(chunks: List[Dict[str, Any]]) -> Optional[float]:
    for chunk in chunks:
        score = chunk.get("rerank_score")
        if score is not None:
            try:
                return float(score)
            except (TypeError, ValueError):
                return None
    return None
