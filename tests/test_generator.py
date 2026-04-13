from __future__ import annotations

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
async def test_stream_yields_tokens_in_order() -> None:
    fake_client = FakeAsyncOpenAIClient()
    fake_client.chat.completions.stream_tokens = ["Alpha", " ", "Beta"]
    gen = Generator(client=fake_client)

    collected: list[str] = []
    async for token in gen.stream(PROMPT, context="ctx", query="q"):
        collected.append(token)
    assert collected == ["Alpha", " ", "Beta"]
    assert fake_client.chat.completions.calls[-1]["stream"] is True
