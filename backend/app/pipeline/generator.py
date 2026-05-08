from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from openai import AsyncOpenAI
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.models.database import get_async_openai_client
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GenerationError(RuntimeError):
    """Raised when LLM generation fails."""


_NO_CITATIONS_ADDENDUM = (
    "\n\nIMPORTANT: Do NOT include any [SOURCE_N] citation markers in your "
    "response. Answer directly without referencing source numbers."
)

_GENERATE_ANSWER_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_answer",
        "description": "Return the answer and the list of source indices cited.",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "cited_sources": {
                    "type": "array",
                    "items": {"type": "integer"},
                },
            },
            "required": ["answer", "cited_sources"],
        },
    },
}

_GENERATE_ANSWER_TOOL_CHOICE = {
    "type": "function",
    "function": {"name": "generate_answer"},
}


def _reconstruct_answer(
    answer: str,
    cited_sources: list[int],
    num_chunks: int,
) -> str:
    """Reconstruct answer string with [SOURCE_N] markers from structured tool output."""
    import re as _re
    # If already has markers, return as-is
    if _re.search(r"\[SOURCE_\d+\]", answer):
        return answer
    # Filter to valid source indices
    valid = [i for i in cited_sources if 1 <= i <= num_chunks]
    if not valid:
        return answer
    markers = "".join(f"[SOURCE_{i}]" for i in sorted(set(valid)))
    return f"{answer} {markers}"


class Generator:
    """Citation-enforced LLM generator wrapping OpenAI chat completions."""

    def __init__(self, client: Optional[AsyncOpenAI] = None) -> None:
        settings = get_settings()
        if client is not None:
            self._client = client
        else:
            try:
                self._client = get_async_openai_client()
            except RuntimeError as exc:
                raise GenerationError(str(exc)) from exc
        self._settings = settings

    def _build_messages(
        self,
        prompt: Dict[str, Any],
        context: str,
        query: str,
        *,
        include_citations: bool = True,
    ) -> List[Dict[str, str]]:
        system = prompt["system_prompt"]
        if not include_citations:
            system = system + _NO_CITATIONS_ADDENDUM
        user_prompt = prompt["user_prompt_template"].format(context=context, query=query)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]

    def _resolve_params(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        meta = prompt.get("metadata") or {}
        return {
            "model": prompt.get("model") or meta.get("model") or self._settings.generation_model,
            "temperature": prompt.get("temperature")
            if prompt.get("temperature") is not None
            else meta.get("temperature", self._settings.generation_temperature),
            "max_tokens": prompt.get("max_tokens")
            or meta.get("max_tokens")
            or self._settings.generation_max_tokens,
        }

    async def _generate_structured(
        self,
        messages: List[Dict[str, Any]],
        params: Dict[str, Any],
        num_chunks: int,
    ) -> str | None:
        """Attempt tool-call generation. Returns reconstructed answer str or None on failure."""
        import json as _json
        try:
            response = await self._client.chat.completions.create(
                model=params["model"],
                messages=messages,
                tools=[_GENERATE_ANSWER_TOOL],
                tool_choice=_GENERATE_ANSWER_TOOL_CHOICE,
                temperature=params["temperature"],
                max_tokens=params["max_tokens"],
                timeout=self._settings.generation_timeout_seconds,
            )
            tool_call = response.choices[0].message.tool_calls[0]
            payload = _json.loads(tool_call.function.arguments)
            answer = payload["answer"]
            cited_sources = payload.get("cited_sources", [])
            return _reconstruct_answer(answer, cited_sources, num_chunks)
        except Exception as exc:
            logger.warning("generator.structured_output_fallback", exc_info=exc)
            return None

    async def generate(
        self,
        prompt: Dict[str, Any],
        context: str,
        query: str,
        *,
        include_citations: bool = True,
        chunks: Optional[List[Any]] = None,
    ) -> str:
        messages = self._build_messages(prompt, context, query, include_citations=include_citations)
        params = self._resolve_params(prompt)

        # Structured output path (when citations requested and enabled)
        if include_citations and self._settings.use_structured_output:
            num_chunks = len(chunks) if chunks is not None else 0
            result = await self._generate_structured(messages, params, num_chunks)
            if result is not None:
                return result
            # Fall through to prose mode on failure

        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=1, max=8),
                retry=retry_if_exception_type(Exception),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=params["model"],
                        temperature=params["temperature"],
                        max_tokens=params["max_tokens"],
                        messages=messages,
                        timeout=self._settings.generation_timeout_seconds,
                    )
                    return response.choices[0].message.content or ""
        except RetryError as exc:  # pragma: no cover - defensive
            raise GenerationError(f"Generation failed after retries: {exc}") from exc
        raise GenerationError("Generation retry loop exited unexpectedly.")

    async def stream(
        self,
        prompt: Dict[str, Any],
        context: str,
        query: str,
        *,
        include_citations: bool = True,
    ) -> AsyncIterator[str]:
        messages = self._build_messages(prompt, context, query, include_citations=include_citations)
        params = self._resolve_params(prompt)
        try:
            stream = await self._client.chat.completions.create(
                model=params["model"],
                temperature=params["temperature"],
                max_tokens=params["max_tokens"],
                messages=messages,
                stream=True,
                timeout=self._settings.generation_timeout_seconds,
            )
        except Exception as exc:
            raise GenerationError(f"Stream initialization failed: {exc}") from exc

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            token = getattr(delta, "content", None)
            if token:
                yield token
