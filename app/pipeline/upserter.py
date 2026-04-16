from __future__ import annotations

from typing import Any, List, Optional

from supabase import Client
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.database import get_service_client
from app.models.schemas import PreparedChunk
from app.utils.logger import get_logger

logger = get_logger(__name__)

UPSERT_BATCH_SIZE = 100


class UpsertError(RuntimeError):
    """Raised when batch upsert into Supabase fails."""


class DocumentUpserter:
    """Batch-inserts chunks + embeddings into the `documents` table."""

    def __init__(self, client: Optional[Client] = None) -> None:
        self._client = client or get_service_client()

    def upsert_chunks(
        self,
        *,
        tenant_id: str,
        job_id: str,
        knowledge_base_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        document_status: str = "active",
        chunks: List[PreparedChunk],
        embeddings: List[List[float]],
    ) -> int:
        if len(chunks) != len(embeddings):
            raise UpsertError(
                f"Chunk/embedding length mismatch: {len(chunks)} vs {len(embeddings)}"
            )
        if not chunks:
            return 0

        inserted = 0
        for start in range(0, len(chunks), UPSERT_BATCH_SIZE):
            batch_chunks = chunks[start : start + UPSERT_BATCH_SIZE]
            batch_embeddings = embeddings[start : start + UPSERT_BATCH_SIZE]
            records = [
                self._build_record(
                    tenant_id=tenant_id,
                    job_id=job_id,
                    knowledge_base_id=knowledge_base_id,
                    source_type=source_type,
                    source_id=source_id,
                    document_status=document_status,
                    chunk=chunk,
                    embedding=embedding,
                )
                for chunk, embedding in zip(batch_chunks, batch_embeddings)
            ]
            self._insert_batch(records)
            inserted += len(records)
            logger.info(
                "upserter.batch.done",
                job_id=job_id,
                tenant_id=tenant_id,
                inserted=len(records),
                total_inserted=inserted,
            )
        return inserted

    def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        total_chunks: Optional[int] = None,
        processed_chunks: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        payload: dict[str, Any] = {"status": status, "updated_at": "now()"}
        if total_chunks is not None:
            payload["total_chunks"] = total_chunks
        if processed_chunks is not None:
            payload["processed_chunks"] = processed_chunks
        if error_message is not None:
            payload["error_message"] = error_message
        self._client.table("ingestion_jobs").update(payload).eq("id", job_id).execute()

    @staticmethod
    def _build_record(
        *,
        tenant_id: str,
        job_id: str,
        knowledge_base_id: Optional[str],
        source_type: Optional[str],
        source_id: Optional[str],
        document_status: str,
        chunk: PreparedChunk,
        embedding: List[float],
    ) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "job_id": job_id,
            "knowledge_base_id": knowledge_base_id,
            "source_type": source_type,
            "source_id": source_id,
            "status": document_status,
            "content": chunk.content,
            "embedding": embedding,
            "metadata": chunk.metadata.model_dump(mode="json"),
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _insert_batch(self, records: List[dict[str, Any]]) -> None:
        try:
            self._client.table("documents").insert(records).execute()
        except Exception as exc:
            logger.error("upserter.insert_failed", error=str(exc), batch_size=len(records))
            raise UpsertError(str(exc)) from exc
