from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.pipeline.generator import Generator
from tests.fakes import FakeAsyncOpenAIClient


PROMPT = {
    "name": "rag_generation_v1",
    "version": 1,
    "system_prompt": "you are a strict assistant",
    "user_prompt_template": "CTX:\n{context}\n\nQ: {query}",
    "metadata": {"model": "gpt-4o", "temperature": 0.1, "max_tokens": 256},
    "model": "gpt-4o",
    "temperature": 0.1,
    "max_tokens": 256,
}


@pytest.mark.asyncio
async def test_generate_returns_full_text_and_uses_prompt_params() -> None:
    fake_client = FakeAsyncOpenAIClient(response_text="The cap is $1M [SOURCE_1].")
    gen = Generator(client=fake_client)

    answer = await gen.generate(PROMPT, context="SRC BODY", query="What is the cap?")

    assert answer == "The cap is $1M [SOURCE_1]."
    call = fake_client.chat.completions.calls[-1]
    assert call["model"] == "gpt-4o"
    assert call["temperature"] == 0.1
    assert call["max_tokens"] == 256
    assert call["messages"][0]["role"] == "system"
    assert "strict assistant" in call["messages"][0]["content"]
    user_msg = call["messages"][1]["content"]
    assert "SRC BODY" in user_msg
    assert "What is the cap?" in user_msg


@pytest.mark.asyncio
async def test_generate_no_citations_appends_suppression_instruction() -> None:
    fake_client = FakeAsyncOpenAIClient(response_text="The cap is $1M.")
    gen = Generator(client=fake_client)

    await gen.generate(PROMPT, context="SRC BODY", query="What is the cap?", include_citations=False)

    system_msg = fake_client.chat.completions.calls[-1]["messages"][0]["content"]
    assert "[SOURCE_N]" in system_msg
    assert "Do NOT include" in system_msg


@pytest.mark.asyncio
async def test_generate_with_citations_does_not_add_suppression() -> None:
    fake_client = FakeAsyncOpenAIClient(response_text="Answer [SOURCE_1].")
    gen = Generator(client=fake_client)

    await gen.generate(PROMPT, context="ctx", query="q", include_citations=True)

    system_msg = fake_client.chat.completions.calls[-1]["messages"][0]["content"]
    assert "Do NOT include" not in system_msg


@pytest.mark.asyncio
async def test_stream_yields_tokens_in_order() -> None:
    fake_client = FakeAsyncOpenAIClient()
    fake_client.chat.completions.stream_tokens = ["Alpha", " ", "Beta"]
    gen = Generator(client=fake_client)

    collected: list[str] = []
    async for token in gen.stream(PROMPT, context="ctx", query="q"):
        collected.append(token)
    assert collected == ["Alpha", " ", "Beta"]
    assert fake_client.chat.completions.calls[-1]["stream"] is True


@pytest.mark.asyncio
async def test_stream_no_citations_injects_suppression_instruction() -> None:
    fake_client = FakeAsyncOpenAIClient()
    fake_client.chat.completions.stream_tokens = ["Hello"]
    gen = Generator(client=fake_client)

    async for _ in gen.stream(PROMPT, context="ctx", query="q", include_citations=False):
        pass

    system_msg = fake_client.chat.completions.calls[-1]["messages"][0]["content"]
    assert "Do NOT include" in system_msg


# ---------------------------------------------------------------------------
# Structured output (tool-call) tests
# ---------------------------------------------------------------------------

def _make_gen_with_structured(response_text: str = "stub") -> tuple[Generator, Any]:
    """Return (generator, fake_client) with use_structured_output=True (default)."""
    fake_client = FakeAsyncOpenAIClient(response_text=response_text)
    gen = Generator(client=fake_client)
    # Ensure use_structured_output is True (override cached settings attribute)
    gen._settings = MagicMock(wraps=gen._settings)
    gen._settings.use_structured_output = True
    return gen, fake_client


@pytest.mark.asyncio
async def test_generate_structured_output_adds_citations() -> None:
    """Tool-call response → correct [SOURCE_N] markers in output string."""
    tool_payload = json.dumps({"answer": "The cap is $1M.", "cited_sources": [1, 3]})
    gen, fake_client = _make_gen_with_structured()
    fake_client.chat.completions.tool_response = tool_payload

    chunks = ["chunk1", "chunk2", "chunk3"]
    result = await gen.generate(PROMPT, context="ctx", query="q", include_citations=True, chunks=chunks)

    assert "The cap is $1M." in result
    assert "[SOURCE_1]" in result
    assert "[SOURCE_3]" in result


@pytest.mark.asyncio
async def test_generate_structured_output_drops_out_of_range_sources() -> None:
    """cited_sources with out-of-range indices are silently dropped."""
    tool_payload = json.dumps({"answer": "The cap is $1M.", "cited_sources": [1, 5]})
    gen, fake_client = _make_gen_with_structured()
    fake_client.chat.completions.tool_response = tool_payload

    chunks = ["chunk1", "chunk2", "chunk3"]  # only 3 chunks
    result = await gen.generate(PROMPT, context="ctx", query="q", include_citations=True, chunks=chunks)

    assert "[SOURCE_1]" in result
    assert "[SOURCE_5]" not in result


@pytest.mark.asyncio
async def test_generate_structured_output_fallback_on_malformed_response(caplog) -> None:
    """Malformed tool response → falls back to prose mode, warning logged."""
    gen, fake_client = _make_gen_with_structured(response_text="prose fallback answer")
    fake_client.chat.completions.tool_response = "THIS IS NOT VALID JSON {{{"

    with caplog.at_level(logging.WARNING):
        result = await gen.generate(PROMPT, context="ctx", query="q", include_citations=True, chunks=["c1"])

    # Should have fallen back to prose and returned the normal response
    assert result == "prose fallback answer"
    assert any("structured_output_fallback" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_generate_structured_output_disabled_skips_tool_call() -> None:
    """use_structured_output=False → prose path invoked, no tool call made."""
    tool_payload = json.dumps({"answer": "Should not appear.", "cited_sources": [1]})
    fake_client = FakeAsyncOpenAIClient(response_text="prose answer")
    gen = Generator(client=fake_client)
    # Disable structured output
    gen._settings = MagicMock(wraps=gen._settings)
    gen._settings.use_structured_output = False
    fake_client.chat.completions.tool_response = tool_payload  # would be used if structured path ran

    result = await gen.generate(PROMPT, context="ctx", query="q", include_citations=True, chunks=["c1"])

    # tool_response should NOT have been used; prose path returns prose answer
    assert result == "prose answer"
    # Verify no tool_choice was sent in any call
    for call in fake_client.chat.completions.calls:
        assert "tools" not in call


@pytest.mark.asyncio
async def test_generate_decline_with_empty_sources_no_markers() -> None:
    """Decline answer + empty cited_sources → no [SOURCE_N] markers appended."""
    tool_payload = json.dumps({"answer": "I don't have enough information.", "cited_sources": []})
    gen, fake_client = _make_gen_with_structured()
    fake_client.chat.completions.tool_response = tool_payload

    result = await gen.generate(PROMPT, context="ctx", query="q", include_citations=True, chunks=["c1"])

    assert "I don't have enough information." in result
    import re
    assert not re.search(r"\[SOURCE_\d+\]", result)
