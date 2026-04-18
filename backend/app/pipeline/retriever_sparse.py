from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from app.models.database import get_service_client
from app.pipeline.retriever_dense import DenseRetrievalError, DenseRetriever
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SparseRetrievalError(RuntimeError):
    """Raised when sparse full-text retrieval fails."""


class SparseRetriever:
    """BM25-equivalent retrieval via Postgres `tsvector` + `ts_rank`.

    Phase 2 uses the `match_documents_hybrid` RPC for the fused path; this
    class exposes sparse-only retrieval for tests and for the in-Python RRF
    path used when the SQL function is unavailable.
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client or get_service_client()

    async def retrieve(
        self,
        query_text: str,
        tenant_id: str,
        integration_id: Optional[str] = None,
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        params = {
            "query_text": query_text,
            "match_count": top_n,
            "filter_tenant_id": tenant_id,
            "filter_integration_id": integration_id,
        }
        try:
            response = await asyncio.to_thread(
                lambda: self._client.rpc("match_documents_sparse", params).execute()
            )
        except Exception as exc:
            logger.error("sparse_retriever.rpc_failed", tenant_id=tenant_id, error=str(exc))
            raise SparseRetrievalError(str(exc)) from exc

        rows = response.data or []
        results: List[Dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row.get("metadata") or {},
                    "ts_rank": float(row.get("ts_rank") or 0.0),
                    "sparse_rank": rank,
                }
            )
        return results


class HybridRetriever:
    """Calls the `match_documents_hybrid` RPC that fuses dense + sparse via RRF.

    Supports OpenAI-style weighted RRF: ``semantic_weight`` and
    ``full_text_weight`` bias the contribution of the dense and sparse
    ranklists respectively. Defaults come from app settings and can be
    overridden per call (e.g. for keyword-heavy corpora like code).
    """

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client or get_service_client()

    async def retrieve(
        self,
        query_embedding: List[float],
        query_text: str,
        tenant_id: str,
        integration_id: Optional[str] = None,
        match_count: int = 20,
        rrf_k: int = 60,
        dense_top_n: int = 20,
        sparse_top_n: int = 20,
        semantic_weight: Optional[float] = None,
        full_text_weight: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        from app.config import get_settings

        settings = get_settings()
        sw = settings.semantic_weight if semantic_weight is None else semantic_weight
        fw = settings.full_text_weight if full_text_weight is None else full_text_weight

        params = {
            "query_embedding": query_embedding,
            "query_text": query_text,
            "match_count": match_count,
            "rrf_k": rrf_k,
            "dense_top_n": dense_top_n,
            "sparse_top_n": sparse_top_n,
            "filter_tenant_id": tenant_id,
            "filter_integration_id": integration_id,
            "semantic_weight": sw,
            "full_text_weight": fw,
        }
        try:
            response = await asyncio.to_thread(
                lambda: self._client.rpc("match_documents_hybrid", params).execute()
            )
        except Exception as exc:
            message = str(exc)
            if _is_missing_weighted_rpc_error(message):
                # Older DB that doesn't know about the weighted params yet.
                # Retry without them — equivalent to equal-weight RRF.
                logger.warning(
                    "hybrid_retriever.rpc_weights_unsupported_retry_unweighted",
                    tenant_id=tenant_id,
                    error=message,
                )
                legacy_params = {
                    k: v
                    for k, v in params.items()
                    if k not in ("semantic_weight", "full_text_weight")
                }
                try:
                    response = await asyncio.to_thread(
                        lambda: self._client.rpc(
                            "match_documents_hybrid", legacy_params
                        ).execute()
                    )
                except Exception as retry_exc:  # pragma: no cover - defensive
                    message = str(retry_exc)
                    exc = retry_exc
                else:
                    rows = response.data or []
                    return [
                        {
                            "id": row["id"],
                            "content": row["content"],
                            "metadata": row.get("metadata") or {},
                            "rrf_score": float(row.get("rrf_score") or 0.0),
                            "dense_rank": int(row.get("dense_rank") or 0),
                            "sparse_rank": int(row.get("sparse_rank") or 0),
                        }
                        for row in rows
                    ]
            if _is_missing_hybrid_rpc_error(message):
                logger.warning(
                    "hybrid_retriever.rpc_missing_fallback_dense",
                    tenant_id=tenant_id,
                    error=message,
                )
                try:
                    dense_results = await DenseRetriever(client=self._client).retrieve(
                        query_embedding=query_embedding,
                        tenant_id=tenant_id,
                        integration_id=integration_id,
                        top_n=match_count,
                    )
                except DenseRetrievalError as dense_exc:
                    logger.error(
                        "hybrid_retriever.dense_fallback_failed",
                        tenant_id=tenant_id,
                        error=str(dense_exc),
                    )
                    raise SparseRetrievalError(str(dense_exc)) from dense_exc

                return [
                    {
                        "id": row["id"],
                        "content": row["content"],
                        "metadata": row.get("metadata") or {},
                        # Dense fallback has no sparse rank and no true RRF score.
                        "rrf_score": float(row.get("similarity") or 0.0),
                        "dense_rank": int(row.get("dense_rank") or 0),
                        "sparse_rank": 0,
                    }
                    for row in dense_results
                ]

            logger.error("hybrid_retriever.rpc_failed", tenant_id=tenant_id, error=message)
            raise SparseRetrievalError(message) from exc

        rows = response.data or []
        results: List[Dict[str, Any]] = []
        for row in rows:
            results.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row.get("metadata") or {},
                    "rrf_score": float(row.get("rrf_score") or 0.0),
                    "dense_rank": int(row.get("dense_rank") or 0),
                    "sparse_rank": int(row.get("sparse_rank") or 0),
                }
            )
        return results


def _is_missing_hybrid_rpc_error(message: str) -> bool:
    return "PGRST202" in message or "Could not find the function public.match_documents_hybrid" in message


def _is_missing_weighted_rpc_error(message: str) -> bool:
    """Detect a PostgREST schema-cache miss for the weighted-RRF signature.

    When the DB has the unweighted function but not the weighted one,
    PostgREST returns PGRST202 while naming the `semantic_weight` /
    `full_text_weight` params it could not match. We retry without them.
    """
    if "PGRST202" not in message:
        return False
    return "semantic_weight" in message or "full_text_weight" in message
