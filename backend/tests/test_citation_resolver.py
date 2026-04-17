from __future__ import annotations

import uuid

from app.pipeline.citation_resolver import (
    assemble_context,
    resolve_citations,
)


def _chunk(idx: int) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "content": f"chunk body {idx}",
        "metadata": {
            "document_title": f"Doc {idx}",
            "section_heading": f"Section {idx}",
            "page_number": idx + 1,
        },
        "rerank_score": 0.9 - idx * 0.1,
        "rrf_score": 0.05 - idx * 0.01,
    }


def test_assemble_context_injects_source_headers() -> None:
    chunks = [_chunk(0), _chunk(1)]
    text = assemble_context(chunks)
    assert "[SOURCE_1]" in text
    assert "[SOURCE_2]" in text
    assert "Doc 0" in text
    assert "Section 1" in text
    assert "chunk body 1" in text


def test_resolve_citations_extracts_only_cited_indices() -> None:
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    response = "A claim [SOURCE_1]. Another [SOURCE_3]."
    citations = resolve_citations(response, chunks)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_3"]
    assert citations[0].chunk_id == uuid.UUID(chunks[0]["id"])
    assert citations[0].rerank_score == chunks[0]["rerank_score"]


def test_resolve_citations_include_uncited_returns_all() -> None:
    chunks = [_chunk(0), _chunk(1)]
    citations = resolve_citations("", chunks, include_uncited=True)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_2"]


def test_resolve_citations_ignores_out_of_range() -> None:
    chunks = [_chunk(0)]
    citations = resolve_citations("foo [SOURCE_5]", chunks)
    assert citations == []
