from __future__ import annotations

from typing import Any, Dict, List

import pytest

from app.pipeline.reranker import Reranker, RerankerError, check_relevance


class _StubBackend:
    def __init__(self, provider: str, scores: List[float], raise_exc: bool = False) -> None:
        self.provider = provider
        self._scores = scores
        self._raise = raise_exc
        self.calls = 0

    def rerank(
        self, query: str, chunks: List[Dict[str, Any]], top_k: int
    ) -> List[Dict[str, Any]]:
        self.calls += 1
        if self._raise:
            raise RuntimeError("boom")
        out = []
        for chunk, score in zip(chunks, self._scores):
            entry = dict(chunk)
            entry["rerank_score"] = score
            out.append(entry)
        out.sort(key=lambda x: x["rerank_score"], reverse=True)
        return out[:top_k]


def _chunks() -> List[Dict[str, Any]]:
    return [
        {"id": "1", "content": "alpha", "metadata": {}},
        {"id": "2", "content": "beta", "metadata": {}},
        {"id": "3", "content": "gamma", "metadata": {}},
    ]


def test_reranker_uses_primary_and_returns_provider() -> None:
    primary = _StubBackend("cohere", [0.9, 0.5, 0.1])
    rr = Reranker(primary=primary, fallback=_StubBackend("local", [0.0, 0.0, 0.0]))
    results, provider = rr.rerank("q", _chunks(), top_k=2)
    assert provider == "cohere"
    assert primary.calls == 1
    assert [r["id"] for r in results] == ["1", "2"]
    assert results[0]["rerank_score"] == 0.9


def test_reranker_falls_back_on_primary_failure() -> None:
    primary = _StubBackend("cohere", [], raise_exc=True)
    fallback = _StubBackend("local", [0.7, 0.2, 0.4])
    rr = Reranker(primary=primary, fallback=fallback)
    results, provider = rr.rerank("q", _chunks(), top_k=2)
    assert provider == "local_fallback"
    assert fallback.calls == 1
    assert [r["id"] for r in results] == ["1", "3"]


def test_reranker_raises_when_both_backends_fail() -> None:
    primary = _StubBackend("cohere", [], raise_exc=True)
    fallback = _StubBackend("local", [], raise_exc=True)
    rr = Reranker(primary=primary, fallback=fallback)
    with pytest.raises(RerankerError):
        rr.rerank("q", _chunks(), top_k=2)


def test_check_relevance_enforces_threshold() -> None:
    assert check_relevance([{"rerank_score": 0.5}], threshold=0.25) is True
    assert check_relevance([{"rerank_score": 0.1}], threshold=0.25) is False
    assert check_relevance([], threshold=0.25) is False
    # Missing score means we can't reject — err on permissive side.
    assert check_relevance([{}], threshold=0.25) is True
