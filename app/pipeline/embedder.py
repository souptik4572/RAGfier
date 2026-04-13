from __future__ import annotations

from typing import List, Optional

from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingError(RuntimeError):
    """Raised when embedding generation fails."""


class Embedder:
    """OpenAI batch embedder with exponential-backoff retries."""

    def __init__(
        self,
        client: Optional[AsyncOpenAI] = None,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        if client is not None:
            self._client = client
        else:
            if not settings.openai_api_key:
                raise EmbeddingError("OPENAI_API_KEY is not configured.")
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = model or settings.openai_embedding_model
        self._batch_size = batch_size or settings.embedding_batch_size

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        all_embeddings: List[List[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            logger.info(
                "embedder.batch.start",
                batch_index=start // self._batch_size,
                batch_size=len(batch),
            )
            batch_embeddings = await self._embed_with_retry(batch)
            all_embeddings.extend(batch_embeddings)
        return all_embeddings

    async def embed_query(self, text: str) -> List[float]:
        result = await self.embed_texts([text])
        if not result:
            raise EmbeddingError("Embedding query returned no result.")
        return result[0]

    async def _embed_with_retry(self, batch: List[str]) -> List[List[float]]:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.embeddings.create(
                        model=self._model,
                        input=batch,
                    )
                    return [item.embedding for item in response.data]
        except RetryError as exc:  # pragma: no cover - defensive
            raise EmbeddingError(f"Embedding failed after retries: {exc}") from exc
        raise EmbeddingError("Embedding retry loop exited unexpectedly.")
