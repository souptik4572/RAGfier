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
        self, prompt: Dict[str, Any], context: str, query: str
    ) -> List[Dict[str, str]]:
        user_prompt = prompt["user_prompt_template"].format(context=context, query=query)
        return [
            {"role": "system", "content": prompt["system_prompt"]},
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

    async def generate(
        self, prompt: Dict[str, Any], context: str, query: str
    ) -> str:
        messages = self._build_messages(prompt, context, query)
        params = self._resolve_params(prompt)
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
        self, prompt: Dict[str, Any], context: str, query: str
    ) -> AsyncIterator[str]:
        messages = self._build_messages(prompt, context, query)
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
