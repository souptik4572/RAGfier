from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

from app.models.database import get_service_client
from app.pipeline.chunker import Chunker
from app.pipeline.embedder import Embedder
from app.pipeline.parser import DocumentParser, ParserError
from app.pipeline.upserter import DocumentUpserter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionOrchestrator:
    """Coordinates parse → chunk → embed → upsert for a single ingestion job.

    The pipeline updates `ingestion_jobs.status` at every step so clients
    polling `/status/{job_id}` see meaningful progress.
    """

    def __init__(
        self,
        parser: Optional[DocumentParser] = None,
        chunker: Optional[Chunker] = None,
        embedder: Optional[Embedder] = None,
        upserter: Optional[DocumentUpserter] = None,
    ) -> None:
        self._parser = parser or DocumentParser()
        self._chunker = chunker or Chunker()
        self._embedder = embedder or Embedder()
        self._upserter = upserter or DocumentUpserter()

    async def run(
        self,
        *,
        job_id: str,
        tenant_id: str,
        knowledge_base_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        file_path: str,
        file_name: str,
        file_type: str,
        document_title: Optional[str] = None,
    ) -> None:
        log_ctx = {"job_id": job_id, "tenant_id": tenant_id, "file_name": file_name}
        started = time.perf_counter()
        logger.info("pipeline.start", **log_ctx)

        try:
            # --- Parse ---
            # Every update_job_status call makes a blocking Supabase HTTP
            # request. Push those through to_thread so a slow status write
            # doesn't stall the event loop (which may be servicing other
            # ingestion jobs in parallel via BackgroundTasks).
            await asyncio.to_thread(
                self._upserter.update_job_status, job_id=job_id, status="parsing"
            )
            parse_started = time.perf_counter()
            blocks = await self._parser.parse(file_path, file_type)
            logger.info(
                "pipeline.parsed",
                duration_s=round(time.perf_counter() - parse_started, 3),
                block_count=len(blocks),
                **log_ctx,
            )

            # --- Chunk ---
            await asyncio.to_thread(
                self._upserter.update_job_status, job_id=job_id, status="chunking"
            )
            chunk_started = time.perf_counter()
            chunks = await asyncio.to_thread(
                self._chunker.chunk,
                blocks,
                source=file_name,
                document_id=job_id,
                document_title=document_title,
            )
            logger.info(
                "pipeline.chunked",
                duration_s=round(time.perf_counter() - chunk_started, 3),
                chunk_count=len(chunks),
                **log_ctx,
            )
            if not chunks:
                raise ParserError("No chunks produced from document.")

            await asyncio.to_thread(
                self._upserter.update_job_status,
                job_id=job_id,
                status="embedding",
                total_chunks=len(chunks),
                processed_chunks=0,
            )

            # --- Embed ---
            embed_started = time.perf_counter()
            embeddings = await self._embedder.embed_texts(
                [chunk.content for chunk in chunks]
            )
            logger.info(
                "pipeline.embedded",
                duration_s=round(time.perf_counter() - embed_started, 3),
                embedding_count=len(embeddings),
                **log_ctx,
            )

            # --- Upsert ---
            upsert_started = time.perf_counter()
            inserted = await asyncio.to_thread(
                self._upserter.upsert_chunks,
                tenant_id=tenant_id,
                job_id=job_id,
                knowledge_base_id=knowledge_base_id,
                source_type=source_type,
                source_id=source_id,
                chunks=chunks,
                embeddings=embeddings,
            )
            logger.info(
                "pipeline.upserted",
                duration_s=round(time.perf_counter() - upsert_started, 3),
                inserted=inserted,
                **log_ctx,
            )

            await asyncio.to_thread(
                self._upserter.update_job_status,
                job_id=job_id,
                status="completed",
                total_chunks=len(chunks),
                processed_chunks=inserted,
            )
            logger.info(
                "pipeline.completed",
                duration_s=round(time.perf_counter() - started, 3),
                **log_ctx,
            )
        except Exception as exc:
            logger.exception("pipeline.failed", error=str(exc), **log_ctx)
            try:
                await asyncio.to_thread(
                    self._upserter.update_job_status,
                    job_id=job_id,
                    status="failed",
                    error_message=str(exc),
                )
            except Exception as update_exc:  # pragma: no cover - defensive
                logger.error(
                    "pipeline.status_update_failed",
                    error=str(update_exc),
                    **log_ctx,
                )
            raise
        finally:
            # Best-effort cleanup of the temp file on disk.
            try:
                Path(file_path).unlink(missing_ok=True)
            except Exception:  # pragma: no cover - defensive
                pass


async def run_pipeline_task(
    *,
    job_id: str,
    tenant_id: str,
    knowledge_base_id: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    file_path: str,
    file_name: str,
    file_type: str,
    document_title: Optional[str] = None,
) -> None:
    """Entry point invoked by FastAPI's BackgroundTasks."""
    orchestrator = IngestionOrchestrator()
    try:
        await orchestrator.run(
            job_id=job_id,
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            file_name=file_name,
            file_type=file_type,
            document_title=document_title,
        )
    except Exception:
        # Already logged and persisted inside orchestrator.run; swallow to
        # avoid killing the background task loop.
        pass
