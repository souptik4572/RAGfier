"""Anthropic-style Contextual Retrieval.

Given a document + a chunk extracted from it, ask Claude Haiku for a short
(≤100 token) situating summary and prepend it to the chunk. This fixes the
"lost in a chunk" problem where retrieval misses a chunk because pronouns
or quantities lose their referent once separated from the parent document
(e.g. "Revenue grew 10%" vs. "Acme Corp Q3 2024: revenue grew 10%").

Key implementation details:

- Prompt caching (``cache_control: {type: ephemeral}``) is applied to the
  ``<document>`` block so the same document is billed once per 5-minute
  window and every chunk's call reads from the cache. With per-doc
  chunk counts of tens to hundreds, this is the difference between a
  viable production cost and a prohibitive one.
- The feature is *opt-in* via ``settings.contextualization_enabled`` and
  the presence of ``ANTHROPIC_API_KEY``. If either is missing, the
  contextualizer is a no-op and returns chunks unchanged. This keeps
  existing tests + existing ingestion pipelines working without any
  config change.
- Every network failure is swallowed and logged; the caller never sees
  ingestion crash because Anthropic was flaky.
"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

from app.config import get_settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


_CHUNK_PROMPT_SUFFIX = (
    "Here is the chunk we want to situate within the whole document:\n"
    "<chunk>\n{chunk}\n</chunk>\n"
    "Give a short, succinct context (under 100 words) that situates this "
    "chunk within the overall document for the purposes of improving "
    "search retrieval of the chunk. Include the document's subject, the "
    "surrounding section or topic, and any entities / dates / identifiers "
    "that the chunk itself elides but would need to be retrievable by. "
    "Answer only with the succinct context and nothing else."
)


class ContextualizerError(RuntimeError):
    """Raised when contextualization is requested but cannot be performed."""


class Contextualizer:
    """Prepend per-chunk situated context using Claude Haiku + prompt caching.

    Example::

        contextualizer = Contextualizer()
        enriched = await contextualizer.contextualize_chunks(
            document_text=full_doc_text,
            chunks=[c.content for c in prepared_chunks],
        )
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self._settings = settings
        self._model = model or settings.contextualizer_model
        self._max_tokens = max_tokens or settings.contextualizer_max_tokens
        self._max_concurrency = max_concurrency or settings.contextualizer_max_concurrency
        self._max_doc_chars = settings.contextualizer_max_doc_chars

        # Enabled iff (a) toggle is on and (b) we have an Anthropic client or
        # an API key to build one. A missing SDK is fatal for opt-in use and
        # benign for the default path.
        self._enabled = bool(settings.contextualization_enabled)
        self._client: Optional[Any] = client
        if self._enabled and self._client is None:
            self._client = self._build_client()
            if self._client is None:
                # Couldn't construct a client; downgrade to no-op for this
                # ingestion run without failing the whole job.
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _build_client(self) -> Optional[Any]:
        if not self._settings.anthropic_api_key:
            logger.info(
                "contextualizer.disabled_missing_api_key",
                reason="ANTHROPIC_API_KEY not configured",
            )
            return None
        try:
            from anthropic import AsyncAnthropic  # type: ignore
        except ImportError as exc:
            logger.warning(
                "contextualizer.disabled_sdk_missing",
                error=str(exc),
                hint="pip install anthropic",
            )
            return None
        try:
            return AsyncAnthropic(api_key=self._settings.anthropic_api_key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("contextualizer.client_init_failed", error=str(exc))
            return None

    async def contextualize_chunks(
        self,
        *,
        document_text: str,
        chunks: List[str],
    ) -> List[str]:
        """Return chunks with a ``[Context: …]`` prefix prepended.

        If the contextualizer is disabled (no API key, SDK missing, flag
        off), returns ``chunks`` unchanged so the caller can stay oblivious
        to whether the feature is on.
        """
        if not self._enabled or not chunks:
            return list(chunks)

        # Cap document size. Claude Haiku's 200k window is huge but resume /
        # contract / article-length docs fit in <200k chars easily, and we
        # want a hard ceiling so ingestion of a pathological PDF never
        # sends megabytes to Anthropic per chunk.
        doc = (
            document_text
            if len(document_text) <= self._max_doc_chars
            else document_text[: self._max_doc_chars] + "\n…[truncated]"
        )

        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def run_one(idx: int, chunk: str) -> str:
            async with semaphore:
                summary = await self._summarize(doc, chunk)
            if not summary:
                return chunk
            return f"[Context: {summary}]\n{chunk}"

        enriched = await asyncio.gather(
            *(run_one(i, c) for i, c in enumerate(chunks)),
            return_exceptions=False,
        )
        return list(enriched)

    async def _summarize(self, document_text: str, chunk: str) -> str:
        """Call Claude Haiku to situate ``chunk`` inside ``document_text``.

        The document content block carries ``cache_control: ephemeral`` so
        every subsequent chunk's call is a cache read on the Anthropic
        side, cutting input-token cost by ~90% and latency substantially.
        """
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"<document>\n{document_text}\n</document>",
                                "cache_control": {"type": "ephemeral"},
                            },
                            {
                                "type": "text",
                                "text": _CHUNK_PROMPT_SUFFIX.format(chunk=chunk),
                            },
                        ],
                    }
                ],
            )
        except Exception as exc:
            logger.warning("contextualizer.call_failed", error=str(exc))
            return ""

        try:
            # Claude returns a list of content blocks; the first text block
            # is the summary. Strip whitespace + any accidental quotes.
            blocks = getattr(response, "content", None) or []
            text_parts: list[str] = []
            for block in blocks:
                text = getattr(block, "text", None)
                if text:
                    text_parts.append(text)
            summary = " ".join(text_parts).strip().strip('"').strip()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("contextualizer.parse_failed", error=str(exc))
            return ""

        return summary
