from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import AuthContext, get_auth_context
from app.models.database import get_service_client
from app.models.schemas import QueryRequest, QueryResponse, QueryResult
from app.pipeline.embedder import Embedder, EmbeddingError
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_documents(
    payload: QueryRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> QueryResponse:
    try:
        embedder = Embedder()
        query_embedding = await embedder.embed_query(payload.query)
    except EmbeddingError as exc:
        logger.error("query.embed_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to embed query.") from exc

    client = get_service_client()
    try:
        rpc_response = client.rpc(
            "match_documents",
            {
                "query_embedding": query_embedding,
                "match_count": payload.match_count,
                "filter_tenant_id": auth.tenant_id,
            },
        ).execute()
    except Exception as exc:
        logger.error("query.rpc_failed", tenant_id=auth.tenant_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Retrieval failed.") from exc

    rows = rpc_response.data or []
    results = [
        QueryResult(
            id=UUID(row["id"]),
            content=row["content"],
            metadata=row.get("metadata") or {},
            similarity=float(row.get("similarity") or 0.0),
        )
        for row in rows
    ]

    logger.info(
        "query.completed",
        tenant_id=auth.tenant_id,
        match_count=payload.match_count,
        results=len(results),
    )
    return QueryResponse(query=payload.query, results=results)
