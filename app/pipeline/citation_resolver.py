from __future__ import annotations

import re
from typing import Any, Dict, List
from uuid import UUID

from app.models.schemas import Citation

SOURCE_PATTERN = re.compile(r"\[SOURCE_(\d+)\]")
PREVIEW_LEN = 200


def assemble_context(chunks: List[Dict[str, Any]]) -> str:
    """Build a citation-aware context string for the LLM prompt."""
    parts: List[str] = []
    for i, chunk in enumerate(chunks, start=1):
        meta = chunk.get("metadata") or {}
        parts.append(
            f"[SOURCE_{i}]\n"
            f"Document: {meta.get('document_title') or meta.get('source') or 'Unknown'}\n"
            f"Section: {meta.get('section_heading') or 'N/A'}\n"
            f"Page: {meta.get('page_number') if meta.get('page_number') is not None else 'N/A'}\n"
            f"---\n"
            f"{chunk.get('content', '')}"
        )
    return "\n\n".join(parts)


def resolve_citations(
    response_text: str,
    chunks: List[Dict[str, Any]],
    include_uncited: bool = False,
) -> List[Citation]:
    """Extract `[SOURCE_N]` anchors and resolve them to chunk metadata."""
    cited_indices = {int(m) for m in SOURCE_PATTERN.findall(response_text)}
    target_indices: List[int]
    if include_uncited:
        target_indices = list(range(1, len(chunks) + 1))
    else:
        target_indices = sorted(idx for idx in cited_indices if 1 <= idx <= len(chunks))

    citations: List[Citation] = []
    for idx in target_indices:
        chunk = chunks[idx - 1]
        content = str(chunk.get("content", ""))
        preview = content if len(content) <= PREVIEW_LEN else content[:PREVIEW_LEN] + "..."
        citations.append(
            Citation(
                source_id=f"SOURCE_{idx}",
                chunk_id=_coerce_uuid(chunk.get("id")),
                content=preview,
                metadata=chunk.get("metadata") or {},
                rerank_score=chunk.get("rerank_score"),
                rrf_score=chunk.get("rrf_score"),
            )
        )
    return citations


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
