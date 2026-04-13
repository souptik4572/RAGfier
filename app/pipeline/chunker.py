from __future__ import annotations

from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.models.schemas import ChunkMetadata, ParsedBlock, PreparedChunk
from app.pipeline.parser import PARSER_NAME
from app.utils.logger import get_logger
from app.utils.token_counter import count_tokens

logger = get_logger(__name__)

CHUNK_STRATEGY = "recursive_character"
SEPARATORS = ["\n\n", "\n", ". ", " "]


class Chunker:
    """Recursive character splitter with situated-context injection.

    Chunk targets are 600-800 tokens with 100 token overlap. Token
    counting uses tiktoken's cl100k_base encoding.
    """

    def __init__(
        self,
        chunk_size_tokens: Optional[int] = None,
        overlap_tokens: Optional[int] = None,
    ) -> None:
        settings = get_settings()
        self.chunk_size_tokens = chunk_size_tokens or settings.chunk_size_tokens
        self.overlap_tokens = overlap_tokens or settings.chunk_overlap_tokens
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size_tokens,
            chunk_overlap=self.overlap_tokens,
            length_function=count_tokens,
            separators=SEPARATORS,
        )

    def chunk(
        self,
        blocks: List[ParsedBlock],
        *,
        source: str,
        document_id: str,
        document_title: Optional[str],
    ) -> List[PreparedChunk]:
        logger.info(
            "chunker.start",
            source=source,
            document_id=document_id,
            block_count=len(blocks),
        )

        raw: list[tuple[str, ParsedBlock]] = []
        for block in blocks:
            if block.element_type == "heading":
                # Headings are structural; the next block carries them via section_heading.
                continue
            pieces = self._splitter.split_text(block.text)
            for piece in pieces:
                if piece.strip():
                    raw.append((piece, block))

        total = len(raw)
        if total == 0:
            logger.warning("chunker.empty", source=source, document_id=document_id)
            return []

        prepared: List[PreparedChunk] = []
        for idx, (piece, block) in enumerate(raw):
            content = self._inject_context(
                piece,
                document_title=document_title,
                section_heading=block.section_heading,
            )
            if block.page_number is None or block.bounding_boxes is None:
                logger.warning(
                    "chunker.missing_spatial_metadata",
                    source=source,
                    document_id=document_id,
                    chunk_index=idx,
                    has_page=block.page_number is not None,
                    has_bbox=block.bounding_boxes is not None,
                )
            metadata = ChunkMetadata(
                source=source,
                document_id=document_id,
                page_number=block.page_number,
                bounding_boxes=block.bounding_boxes,
                section_heading=block.section_heading,
                document_title=document_title,
                chunk_index=idx,
                total_chunks=total,
                parser=PARSER_NAME,
                chunk_strategy=CHUNK_STRATEGY,
                chunk_size_tokens=count_tokens(content),
                overlap_tokens=self.overlap_tokens,
            )
            prepared.append(PreparedChunk(content=content, metadata=metadata))

        logger.info(
            "chunker.done",
            source=source,
            document_id=document_id,
            chunk_count=len(prepared),
        )
        return prepared

    @staticmethod
    def _inject_context(
        text: str,
        *,
        document_title: Optional[str],
        section_heading: Optional[str],
    ) -> str:
        """Prepend document title and section heading to the chunk.

        This situated-context pattern improves embedding quality by
        giving the model structural awareness of where the chunk sits
        in the document.
        """
        prefix_lines: list[str] = []
        if document_title:
            prefix_lines.append(f"[Document: {document_title}]")
        if section_heading:
            prefix_lines.append(f"[Section: {section_heading}]")
        if not prefix_lines:
            return text
        return "\n".join(prefix_lines) + "\n" + text
