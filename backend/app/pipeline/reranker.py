from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RerankerError(RuntimeError):
    """Raised when reranking fails and no fallback is available."""


class RerankerBackend(Protocol):
    provider: str

    def rerank(
        self, query: str, chunks: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]: ...


class CohereReranker:
    provider = "cohere"

    def __init__(self, client: Optional[Any] = None, model: str = "rerank-english-v3.0") -> None:
        self._model = model
        if client is not None:
            self._client = client
            return
        settings = get_settings()
        if not settings.cohere_api_key:
            raise RerankerError("COHERE_API_KEY is not configured.")
        try:
            import cohere  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RerankerError("cohere package is not installed") from exc
        self._client = cohere.Client(api_key=settings.cohere_api_key)

    def rerank(
        self, query: str, chunks: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        if not chunks:
            return []
        documents = [c["content"] for c in chunks]
        response = self._client.rerank(
            model=self._model,
            query=query,
            documents=documents,
            top_n=min(top_k, len(documents)),
            return_documents=False,
        )
        reranked: List[Dict[str, Any]] = []
        for result in response.results:
            chunk = dict(chunks[result.index])
            chunk["rerank_score"] = float(result.relevance_score)
            reranked.append(chunk)
        return reranked


class LocalCrossEncoderReranker:
    provider = "local"

    def __init__(self, model: Optional[Any] = None, model_name: Optional[str] = None) -> None:
        if model is not None:
            self._model = model
            return
        settings = get_settings()
        name = model_name or settings.local_reranker_model
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RerankerError("sentence-transformers is not installed") from exc
        self._model = CrossEncoder(name)

    def rerank(
        self, query: str, chunks: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        if not chunks:
            return []
        pairs = [(query, chunk["content"]) for chunk in chunks]
        scores = self._model.predict(pairs)
        scored: List[Dict[str, Any]] = []
        for i, score in enumerate(scores):
            entry = dict(chunks[i])
            entry["rerank_score"] = float(score)
            scored.append(entry)
        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]


class Reranker:
    """Facade that picks a backend based on config and falls back on failure."""

    def __init__(
        self,
        primary: Optional[RerankerBackend] = None,
        fallback: Optional[RerankerBackend] = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._settings = get_settings()

    def _get_primary(self) -> RerankerBackend:
        if self._primary is not None:
            return self._primary
        provider = (self._settings.reranker_provider or "cohere").lower()
        if provider == "cohere":
            self._primary = CohereReranker()
        else:
            self._primary = LocalCrossEncoderReranker()
        return self._primary

    def _get_fallback(self) -> Optional[RerankerBackend]:
        if self._fallback is not None:
            return self._fallback
        try:
            self._fallback = LocalCrossEncoderReranker()
        except RerankerError:
            self._fallback = None
        return self._fallback

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> tuple[List[Dict[str, Any]], str]:
        """Rerank ``chunks`` and return (results, provider_used)."""
        if top_k is None:
            top_k = self._settings.rerank_top_k
        if not chunks:
            return [], "none"

        primary = self._get_primary()
        try:
            return primary.rerank(query, chunks, top_k), primary.provider
        except Exception as exc:
            logger.warning(
                "reranker.primary_failed",
                provider=primary.provider,
                error=str(exc),
            )
            fallback = self._get_fallback()
            if fallback is None or fallback is primary:
                raise RerankerError(f"Reranking failed: {exc}") from exc
            try:
                return (
                    fallback.rerank(query, chunks, top_k),
                    f"{fallback.provider}_fallback",
                )
            except Exception as fb_exc:
                logger.error(
                    "reranker.fallback_failed",
                    provider=fallback.provider,
                    error=str(fb_exc),
                )
                raise RerankerError(
                    f"Primary and fallback reranking failed: {fb_exc}"
                ) from fb_exc


def check_relevance(reranked_chunks: List[Dict[str, Any]], threshold: float) -> bool:
    if not reranked_chunks:
        return False
    top = reranked_chunks[0].get("rerank_score")
    if top is None:
        return True
    return top >= threshold
