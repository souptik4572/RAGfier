from __future__ import annotations

from app.models.schemas import ParsedBlock
from app.pipeline.chunker import CHUNK_STRATEGY, Chunker
from app.pipeline.parser import PARSER_NAME
from app.utils.token_counter import count_tokens


def test_chunker_injects_situated_context():
    block = ParsedBlock(
        text="The liability cap shall not exceed $1,000,000 in aggregate.",
        page_number=5,
        bounding_boxes=[[72, 340, 540, 380]],
        section_heading="3.2 Limitation of Liability",
        element_type="paragraph",
    )
    chunker = Chunker(chunk_size_tokens=400, overlap_tokens=40)
    chunks = chunker.chunk(
        [block],
        source="msa.pdf",
        document_id="doc-1",
        document_title="Master Services Agreement",
    )
    assert len(chunks) >= 1
    first = chunks[0]
    assert first.content.startswith("[Document: Master Services Agreement]")
    assert "[Section: 3.2 Limitation of Liability]" in first.content
    assert "liability cap" in first.content


def test_chunker_metadata_shape_and_counts():
    blocks = [
        ParsedBlock(
            text="Paragraph one. " * 20,
            page_number=1,
            bounding_boxes=[[0, 0, 100, 100]],
            section_heading="Intro",
            element_type="paragraph",
        ),
        ParsedBlock(
            text="Paragraph two. " * 20,
            page_number=2,
            bounding_boxes=[[0, 0, 100, 100]],
            section_heading="Body",
            element_type="paragraph",
        ),
    ]
    chunker = Chunker(chunk_size_tokens=700, overlap_tokens=100)
    chunks = chunker.chunk(
        blocks, source="x.md", document_id="doc-42", document_title="Doc"
    )
    total = len(chunks)
    assert total >= 2
    for idx, chunk in enumerate(chunks):
        meta = chunk.metadata
        assert meta.source == "x.md"
        assert meta.document_id == "doc-42"
        assert meta.chunk_index == idx
        assert meta.total_chunks == total
        assert meta.parser == PARSER_NAME
        assert meta.chunk_strategy == CHUNK_STRATEGY
        assert meta.overlap_tokens == 100
        assert meta.chunk_size_tokens == count_tokens(chunk.content)
        assert meta.page_number in {1, 2}


def test_chunker_skips_heading_blocks_but_preserves_section():
    heading = ParsedBlock(
        text="## Section A",
        section_heading="Section A",
        element_type="heading",
    )
    body = ParsedBlock(
        text="Alpha body text.",
        page_number=3,
        bounding_boxes=[[0, 0, 10, 10]],
        section_heading="Section A",
        element_type="paragraph",
    )
    chunker = Chunker()
    chunks = chunker.chunk(
        [heading, body],
        source="s.md",
        document_id="d1",
        document_title=None,
    )
    assert len(chunks) == 1
    assert chunks[0].metadata.section_heading == "Section A"
    assert "Alpha body text." in chunks[0].content
