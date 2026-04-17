from __future__ import annotations

from typing import Any, List

import pytest

from app.pipeline.embedder import Embedder, EmbeddingError


class _FakeEmbeddings:
    def __init__(self, dim: int = 1536) -> None:
        self.calls: list[list[str]] = []
        self.dim = dim

    async def create(self, *, model: str, input: List[str]) -> Any:
        self.calls.append(list(input))

        class _Item:
            def __init__(self, vector: list[float]) -> None:
                self.embedding = vector

        class _Resp:
            def __init__(self, items: list[_Item]) -> None:
                self.data = items

        return _Resp([_Item([float(i) / 1000] * self.dim) for i, _ in enumerate(input)])


class _FakeOpenAI:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


@pytest.mark.asyncio
async def test_embed_texts_batches_requests():
    fake = _FakeOpenAI()
    embedder = Embedder(client=fake, model="text-embedding-3-small", batch_size=3)
    texts = [f"doc-{i}" for i in range(7)]
    vectors = await embedder.embed_texts(texts)

    assert len(vectors) == 7
    assert all(len(v) == 1536 for v in vectors)
    assert [len(b) for b in fake.embeddings.calls] == [3, 3, 1]


@pytest.mark.asyncio
async def test_embed_query_returns_single_vector():
    fake = _FakeOpenAI()
    embedder = Embedder(client=fake, batch_size=100)
    vector = await embedder.embed_query("hello world")
    assert len(vector) == 1536


@pytest.mark.asyncio
async def test_embed_empty_short_circuits():
    fake = _FakeOpenAI()
    embedder = Embedder(client=fake, batch_size=10)
    assert await embedder.embed_texts([]) == []
    assert fake.embeddings.calls == []


@pytest.mark.asyncio
async def test_embed_query_propagates_error():
    class _BrokenEmbeddings:
        async def create(self, **_: Any) -> Any:
            raise RuntimeError("boom")

    class _BrokenClient:
        embeddings = _BrokenEmbeddings()

    embedder = Embedder(client=_BrokenClient(), batch_size=1)
    with pytest.raises(RuntimeError):
        await embedder.embed_query("x")
