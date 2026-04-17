from __future__ import annotations

import pytest

from app.pipeline.parser import DocumentParser, ParserError


@pytest.mark.asyncio
async def test_parse_markdown_tracks_section_heading(tmp_path):
    md = """# Title

Intro paragraph.

## Section A

Alpha content line one.
Alpha content line two.

## Section B

Beta content.
"""
    path = tmp_path / "doc.md"
    path.write_text(md, encoding="utf-8")

    parser = DocumentParser(api_key="dummy")
    blocks = await parser.parse(path, "md")

    paragraph_blocks = [b for b in blocks if b.element_type == "paragraph"]
    assert len(paragraph_blocks) == 3

    headings = [b.section_heading for b in paragraph_blocks]
    assert headings[0] == "Title"
    assert headings[1] == "Section A"
    assert headings[2] == "Section B"

    assert "Alpha content line one." in paragraph_blocks[1].text
    assert "Alpha content line two." in paragraph_blocks[1].text


@pytest.mark.asyncio
async def test_parse_unsupported_type_raises(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("plain text", encoding="utf-8")
    parser = DocumentParser(api_key="dummy")
    with pytest.raises(ParserError):
        await parser.parse(path, "txt")
