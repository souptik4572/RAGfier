from __future__ import annotations

from typing import Any, List

import pytest

from app.pipeline.contextualizer import Contextualizer


class _FakeContentBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeContentBlock(text)]


class _RecordingAnthropicClient:
    """Captures every ``messages.create`` call so we can assert on caching."""

    def __init__(self, reply: str = "Short situated context.") -> None:
        self._reply = reply
        self.calls: List[dict[str, Any]] = []

        outer = self

        class _Messages:
            async def create(self, **kwargs: Any) -> _FakeResponse:
                outer.calls.append(kwargs)
                return _FakeResponse(outer._reply)

        self.messages = _Messages()


@pytest.mark.asyncio
async def test_contextualizer_disabled_by_default_is_noop() -> None:
    contextualizer = Contextualizer()
    assert contextualizer.enabled is False
    out = await contextualizer.contextualize_chunks(
        document_text="Full document body.",
        chunks=["first chunk", "second chunk"],
    )
    assert out == ["first chunk", "second chunk"]


@pytest.mark.asyncio
async def test_contextualizer_prepends_context_and_uses_prompt_caching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import config as config_module

    monkeypatch.setenv("CONTEXTUALIZATION_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config_module.get_settings.cache_clear()

    client = _RecordingAnthropicClient(reply="Resume of Souptik; projects section.")
    contextualizer = Contextualizer(client=client)
    assert contextualizer.enabled is True

    chunks = ["Project Alpha: reduced latency 40%.", "Project Beta: launched chat bot."]
    enriched = await contextualizer.contextualize_chunks(
        document_text="RESUME — Souptik Sarkar …",
        chunks=chunks,
    )

    assert len(enriched) == 2
    for out, original in zip(enriched, chunks):
        assert out.startswith("[Context: Resume of Souptik; projects section.]")
        assert original in out

    # One call per chunk; every call applied `cache_control: ephemeral` to
    # the <document> block so Anthropic will read from the prompt cache.
    assert len(client.calls) == 2
    for call in client.calls:
        first_block = call["messages"][0]["content"][0]
        assert first_block["type"] == "text"
        assert first_block["cache_control"] == {"type": "ephemeral"}
        assert "<document>" in first_block["text"]

    # Tidy up cached settings for other tests.
    monkeypatch.delenv("CONTEXTUALIZATION_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_module.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_contextualizer_falls_back_to_original_chunk_on_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import config as config_module

    monkeypatch.setenv("CONTEXTUALIZATION_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config_module.get_settings.cache_clear()

    class _FailingClient:
        class messages:
            @staticmethod
            async def create(**_: Any) -> _FakeResponse:
                raise RuntimeError("rate limited")

    contextualizer = Contextualizer(client=_FailingClient())
    out = await contextualizer.contextualize_chunks(
        document_text="doc",
        chunks=["chunk-A", "chunk-B"],
    )
    assert out == ["chunk-A", "chunk-B"]

    monkeypatch.delenv("CONTEXTUALIZATION_ENABLED", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config_module.get_settings.cache_clear()
