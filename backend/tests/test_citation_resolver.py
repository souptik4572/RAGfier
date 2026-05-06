from __future__ import annotations

import uuid

import pytest

from app.pipeline.citation_resolver import (
    CitationStreamStripper,
    assemble_context,
    normalize_citation_markers,
    resolve_citations,
    strip_citation_markers,
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


# ---------------------------------------------------------------------------
# assemble_context
# ---------------------------------------------------------------------------

def test_assemble_context_injects_source_headers() -> None:
    chunks = [_chunk(0), _chunk(1)]
    text = assemble_context(chunks)
    assert "[SOURCE_1]" in text
    assert "[SOURCE_2]" in text
    assert "Doc 0" in text
    assert "Section 1" in text
    assert "chunk body 1" in text


# ---------------------------------------------------------------------------
# normalize_citation_markers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    # Canonical — untouched
    ("[SOURCE_1]", "[SOURCE_1]"),
    # Sloppy comma list
    ("[SOURCE_1, SOURCE_2]", "[SOURCE_1][SOURCE_2]"),
    ("[SOURCE_1, SOURCE_2, SOURCE_3]", "[SOURCE_1][SOURCE_2][SOURCE_3]"),
    ("[SOURCE_1; SOURCE_2]", "[SOURCE_1][SOURCE_2]"),
    # Short-form digits in sloppy list
    ("[SOURCE_1, 2, 3]", "[SOURCE_1][SOURCE_2][SOURCE_3]"),
    # Fused bracket (open bracket + digits + prose, no closing ])
    ("[SOURCE_1Foo", "[SOURCE_1]Foo"),
    ("[SOURCE_2Notable", "[SOURCE_2]Notable"),
    # Naked SOURCE_N (no brackets)
    ("SOURCE_1", "[SOURCE_1]"),
    ("SOURCE_1SOURCE_3", "[SOURCE_1][SOURCE_3]"),
    # Mixed normal text
    ("Answer SOURCE_1 and SOURCE_2 explained.", "Answer [SOURCE_1] and [SOURCE_2] explained."),
])
def test_normalize_citation_markers(raw: str, expected: str) -> None:
    assert normalize_citation_markers(raw) == expected


def test_normalize_does_not_double_wrap_canonical() -> None:
    assert normalize_citation_markers("[SOURCE_3]") == "[SOURCE_3]"


# ---------------------------------------------------------------------------
# strip_citation_markers
# ---------------------------------------------------------------------------

def test_strip_removes_canonical() -> None:
    assert strip_citation_markers("Hello [SOURCE_1] world [SOURCE_2].") == "Hello  world ."


def test_strip_removes_malformed_forms() -> None:
    assert strip_citation_markers("Claim SOURCE_1SOURCE_3") == "Claim "
    assert strip_citation_markers("[SOURCE_1Foo") == "Foo"
    assert strip_citation_markers("[SOURCE_1, SOURCE_2] text") == " text"


def test_strip_leaves_plain_text_intact() -> None:
    assert strip_citation_markers("No citations here.") == "No citations here."


# ---------------------------------------------------------------------------
# resolve_citations
# ---------------------------------------------------------------------------

def test_resolve_citations_extracts_only_cited_indices() -> None:
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    response = "A claim [SOURCE_1]. Another [SOURCE_3]."
    citations = resolve_citations(response, chunks)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_3"]
    assert citations[0].chunk_id == uuid.UUID(chunks[0]["id"])
    assert citations[0].rerank_score == chunks[0]["rerank_score"]


def test_resolve_citations_handles_sloppy_list() -> None:
    chunks = [_chunk(0), _chunk(1), _chunk(2)]
    response = "Claim [SOURCE_1, SOURCE_2, SOURCE_3]."
    citations = resolve_citations(response, chunks)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_2", "SOURCE_3"]


def test_resolve_citations_handles_naked_source() -> None:
    chunks = [_chunk(0), _chunk(1)]
    response = "Answer SOURCE_1SOURCE_2"
    citations = resolve_citations(response, chunks)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_2"]


def test_resolve_citations_handles_fused_bracket() -> None:
    chunks = [_chunk(0)]
    response = "[SOURCE_1Notable achievement"
    citations = resolve_citations(response, chunks)
    assert [c.source_id for c in citations] == ["SOURCE_1"]


def test_resolve_citations_include_uncited_returns_all() -> None:
    chunks = [_chunk(0), _chunk(1)]
    citations = resolve_citations("", chunks, include_uncited=True)
    assert [c.source_id for c in citations] == ["SOURCE_1", "SOURCE_2"]


def test_resolve_citations_ignores_out_of_range() -> None:
    chunks = [_chunk(0)]
    citations = resolve_citations("foo [SOURCE_5]", chunks)
    assert citations == []


# ---------------------------------------------------------------------------
# CitationStreamStripper
# ---------------------------------------------------------------------------

def test_stripper_passthrough_plain_text() -> None:
    s = CitationStreamStripper()
    assert s.feed("Hello world") == "Hello world"
    assert s.flush() == ""


def test_stripper_removes_single_token_citation() -> None:
    s = CitationStreamStripper()
    assert s.feed("[SOURCE_1]") == ""
    assert s.flush() == ""


def test_stripper_removes_split_citation() -> None:
    """Citation spans multiple tokens: '[SOURCE_', '1', ']'."""
    s = CitationStreamStripper()
    assert s.feed("[SOURCE_") == ""
    assert s.feed("1") == ""
    assert s.feed("]") == ""
    assert s.flush() == ""


def test_stripper_preserves_text_around_citation() -> None:
    s = CitationStreamStripper()
    assert s.feed("before ") == "before "
    assert s.feed("[SOURCE_2]") == ""
    assert s.feed(" after") == " after"
    assert s.flush() == ""


def test_stripper_handles_inline_brackets_that_are_not_citations() -> None:
    s = CitationStreamStripper()
    out = s.feed("[this is not a citation]")
    assert "[this is not a citation]" in out


def test_stripper_non_citation_bracket_passes_through_immediately() -> None:
    """'[not' has no valid citation prefix so it is emitted by feed(), not held."""
    s = CitationStreamStripper()
    out = s.feed("[not")
    assert "[not" in out
    assert s.flush() == ""


def test_stripper_flush_drains_dangling_citation_partial() -> None:
    """An in-progress '[SOURCE_' at end-of-stream is discarded by flush()."""
    s = CitationStreamStripper()
    assert s.feed("[SOURCE_") == ""
    assert s.flush() == ""
