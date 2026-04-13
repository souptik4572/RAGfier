from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.models.schemas import LatencyBreakdown, RetrievalMetadata
from app.pipeline.citation_resolver import assemble_context
from app.pipeline.embedder import Embedder, EmbeddingError
from app.pipeline.reranker import Reranker, RerankerError, check_relevance
from app.pipeline.retriever_sparse import HybridRetriever, SparseRetrievalError
from app.utils.logger import get_logger
from app.utils.prompt_loader import PromptNotFoundError, load_prompt

logger = get_logger(__name__)

INSUFFICIENT_CONTEXT_MESSAGE = (
    "I don't have enough information in the available documents to answer this question."
)


class QueryPipelineError(RuntimeError):
    """Raised when the hybrid query pipeline cannot proceed."""


@dataclass
class PreparedQuery:
    """Result of the retrieve → rerank → context-assembly stages.

    Wraps everything the generation step needs, plus the metadata and
    decline flag to expose to clients. The non-streaming endpoint runs
    generation inline; the streaming endpoint reuses this same object.
    """

    query: str
    prompt: Dict[str, Any]
    context: str
    final_chunks: List[Dict[str, Any]]
    retrieval_metadata: RetrievalMetadata
    declined: bool = False
    decline_reason: Optional[str] = None
    started_at: float = field(default_factory=time.perf_counter)


async def prepare_query(
    *,
    query: str,
    tenant_id: str,
    match_count: int,
    rerank: bool,
    prompt_name: Optional[str],
    client: Any,
    embedder: Optional[Embedder] = None,
    hybrid_retriever: Optional[HybridRetriever] = None,
    reranker: Optional[Reranker] = None,
) -> PreparedQuery:
    """Run embed → hybrid retrieve → rerank → prompt assembly.

    Returns a :class:`PreparedQuery` ready for generation (or a declined
    response if relevance is insufficient).
    """
    settings = get_settings()
    started = time.perf_counter()
    latency = LatencyBreakdown()

    # Load prompt first so failures don't waste retrieval work.
    name = prompt_name or settings.default_prompt_name
    try:
        prompt = load_prompt(name, tenant_id=tenant_id, client=client)
    except PromptNotFoundError as exc:
        raise QueryPipelineError(f"Prompt '{name}' not found") from exc

    # 1. Embed query.
    t0 = time.perf_counter()
    embedder = embedder or Embedder()
    try:
        query_embedding = await embedder.embed_query(query)
    except EmbeddingError as exc:
        raise QueryPipelineError(f"Embedding failed: {exc}") from exc
    latency.embedding = _ms_since(t0)

    # 2. Hybrid retrieve (dense + sparse + RRF inside the SQL function).
    t0 = time.perf_counter()
    retriever = hybrid_retriever or HybridRetriever(client=client)
    try:
        fused = retriever.retrieve(
            query_embedding=query_embedding,
            query_text=query,
            tenant_id=tenant_id,
            match_count=max(match_count, settings.rerank_top_k, settings.dense_top_n),
            rrf_k=settings.rrf_k,
            dense_top_n=settings.dense_top_n,
            sparse_top_n=settings.sparse_top_n,
        )
    except SparseRetrievalError as exc:
        raise QueryPipelineError(f"Retrieval failed: {exc}") from exc
    latency.retrieval = _ms_since(t0)

    dense_hits = sum(1 for r in fused if r.get("dense_rank"))
    sparse_hits = sum(1 for r in fused if r.get("sparse_rank"))
    rrf_candidates = len(fused)

    # 3. Rerank (optional).
    reranker_provider: Optional[str] = None
    reranked: List[Dict[str, Any]] = fused
    if rerank and fused:
        t0 = time.perf_counter()
        reranker = reranker or Reranker()
        try:
            reranked, reranker_provider = reranker.rerank(
                query=query,
                chunks=fused[: settings.dense_top_n],
                top_k=match_count,
            )
        except RerankerError as exc:
            logger.warning("query_pipeline.rerank_failed", error=str(exc))
            reranked = fused[:match_count]
            reranker_provider = "disabled"
        latency.reranking = _ms_since(t0)
    else:
        reranked = fused[:match_count]

    final_chunks = reranked[:match_count]

    retrieval_metadata = RetrievalMetadata(
        dense_results=dense_hits,
        sparse_results=sparse_hits,
        rrf_candidates=rrf_candidates,
        reranked_top_k=len(final_chunks),
        model=prompt.get("model") or settings.generation_model,
        prompt_version=f"{prompt.get('name', name)}:v{prompt.get('version', 1)}",
        reranker_provider=reranker_provider,
        latency_ms=latency,
    )

    # 4. Hallucination guardrail.
    declined = False
    decline_reason: Optional[str] = None
    if not final_chunks:
        declined = True
        decline_reason = "empty_retrieval"
    elif rerank and not check_relevance(final_chunks, settings.relevance_threshold):
        declined = True
        decline_reason = "below_relevance_threshold"

    context = "" if declined else assemble_context(final_chunks)
    prepared = PreparedQuery(
        query=query,
        prompt=prompt,
        context=context,
        final_chunks=final_chunks,
        retrieval_metadata=retrieval_metadata,
        declined=declined,
        decline_reason=decline_reason,
        started_at=started,
    )
    return prepared


def _ms_since(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def stamp_total_latency(prepared: PreparedQuery) -> None:
    prepared.retrieval_metadata.latency_ms.total = _ms_since(prepared.started_at)
