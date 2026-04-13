from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.database import get_service_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DenseRetrievalError(RuntimeError):
    """Raised when dense vector retrieval fails."""


class DenseRetriever:
    """Cosine-similarity retrieval via the `match_documents` Supabase RPC."""

    def __init__(self, client: Optional[Any] = None) -> None:
        self._client = client or get_service_client()

    def retrieve(
        self,
        query_embedding: List[float],
        tenant_id: str,
        top_n: int = 20,
    ) -> List[Dict[str, Any]]:
        try:
            response = self._client.rpc(
                "match_documents",
                {
                    "query_embedding": query_embedding,
                    "match_count": top_n,
                    "filter_tenant_id": tenant_id,
                },
            ).execute()
        except Exception as exc:
            logger.error("dense_retriever.rpc_failed", tenant_id=tenant_id, error=str(exc))
            raise DenseRetrievalError(str(exc)) from exc

        rows = response.data or []
        results: List[Dict[str, Any]] = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row.get("metadata") or {},
                    "similarity": float(row.get("similarity") or 0.0),
                    "dense_rank": rank,
                }
            )
        return results
