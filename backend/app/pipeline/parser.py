from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any, List, Optional
from xml.etree import ElementTree as ET

from app.config import get_settings
from app.models.schemas import ParsedBlock
from app.utils.logger import get_logger

logger = get_logger(__name__)

PARSER_NAME = "llamaparse"

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


class ParserError(RuntimeError):
    """Raised when document parsing fails."""


class DocumentParser:
    """Layout-aware parser wrapper around LlamaParse.

    Produces a list of `ParsedBlock`s with spatial metadata preserved.
    Markdown input is parsed in-process without an external API call.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or get_settings().llama_cloud_api_key

    async def parse(self, file_path: str | Path, file_type: str) -> List[ParsedBlock]:
        path = Path(file_path)
        file_type = file_type.lower().lstrip(".")
        logger.info("parser.start", file=str(path), file_type=file_type)

        if file_type == "md":
            blocks = self._parse_markdown(path.read_text(encoding="utf-8"))
        elif file_type == "pdf":
            blocks = await self._parse_pdf(path)
        elif file_type == "docx":
            blocks = self._parse_docx(path)
        else:
            raise ParserError(f"Unsupported file type: {file_type}")

        logger.info("parser.done", file=str(path), block_count=len(blocks))
        return blocks

    async def _parse_pdf(self, path: Path) -> List[ParsedBlock]:
        if not self._api_key:
            raise ParserError("LLAMA_CLOUD_API_KEY is not configured.")
        try:
            from llama_parse import LlamaParse  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ParserError("llama-parse package is not installed.") from exc

        parser = LlamaParse(
            api_key=self._api_key,
            result_type="markdown",
            parsing_instruction=(
                "Extract all text preserving section hierarchy. "
                "Preserve table structures as Markdown tables. "
                "Identify and tag all headers with their level."
            ),
            verbose=False,
        )
        try:
            documents: List[Any] = await parser.aload_data(str(path))
        except Exception as exc:  # pragma: no cover - network path
            raise ParserError(f"LlamaParse failed: {exc}") from exc

        blocks: List[ParsedBlock] = []
        for doc in documents:
            text = getattr(doc, "text", None) or ""
            meta = getattr(doc, "metadata", {}) or {}
            page_number = meta.get("page_number") or meta.get("page")
            bbox = meta.get("bbox") or meta.get("bounding_boxes")
            section_heading = meta.get("section_heading")

            for block in self._parse_markdown(text):
                if block.page_number is None:
                    block.page_number = page_number
                if block.bounding_boxes is None and bbox is not None:
                    block.bounding_boxes = bbox if isinstance(bbox, list) else [bbox]
                if block.section_heading is None and section_heading:
                    block.section_heading = section_heading
                blocks.append(block)

        if not blocks:
            raise ParserError("Parser returned no content.")
        return blocks

    def _parse_docx(self, path: Path) -> List[ParsedBlock]:
        """Parse DOCX text content with basic heading detection.

        DOCX does not expose spatial metadata comparable to PDF in this
        parser path, so page_number/bounding_boxes remain unset.
        """
        try:
            with zipfile.ZipFile(path) as archive:
                xml_bytes = archive.read("word/document.xml")
        except KeyError as exc:
            raise ParserError("DOCX is missing word/document.xml") from exc
        except zipfile.BadZipFile as exc:
            raise ParserError("Invalid DOCX file format") from exc
        except Exception as exc:
            raise ParserError(f"Failed to read DOCX: {exc}") from exc

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise ParserError("Unable to parse DOCX XML") from exc

        ns = {"w": _WORD_NS}
        blocks: List[ParsedBlock] = []
        current_heading: Optional[str] = None

        paragraphs = root.findall(".//w:body/w:p", ns)
        for paragraph in paragraphs:
            text_parts = [
                node.text or ""
                for node in paragraph.findall(".//w:t", ns)
            ]
            text = "".join(text_parts).strip()
            if not text:
                continue

            style_node = paragraph.find("./w:pPr/w:pStyle", ns)
            style_value = (style_node.get(f"{{{_WORD_NS}}}val") if style_node is not None else "") or ""
            normalized_style = style_value.strip().lower()
            is_heading = normalized_style.startswith("heading")

            if is_heading:
                current_heading = text
                blocks.append(
                    ParsedBlock(
                        text=text,
                        section_heading=current_heading,
                        element_type="heading",
                    )
                )
            else:
                blocks.append(
                    ParsedBlock(
                        text=text,
                        section_heading=current_heading,
                        element_type="paragraph",
                    )
                )

        if not blocks:
            raise ParserError("DOCX parser returned no content.")

        return blocks

    def _parse_markdown(self, text: str) -> List[ParsedBlock]:
        """Split markdown into blocks while tracking the nearest heading."""
        blocks: List[ParsedBlock] = []
        current_heading: Optional[str] = None
        buffer: list[str] = []

        def flush() -> None:
            nonlocal buffer
            if buffer:
                body = "\n".join(buffer).strip()
                if body:
                    blocks.append(
                        ParsedBlock(
                            text=body,
                            section_heading=current_heading,
                            element_type="paragraph",
                        )
                    )
                buffer = []

        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            header_match = _HEADER_RE.match(line)
            if header_match:
                flush()
                current_heading = header_match.group(2).strip()
                blocks.append(
                    ParsedBlock(
                        text=line,
                        section_heading=current_heading,
                        element_type="heading",
                    )
                )
                continue
            if not line.strip():
                flush()
                continue
            buffer.append(line)
        flush()

        return blocks
