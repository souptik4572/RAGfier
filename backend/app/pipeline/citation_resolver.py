from __future__ import annotations

import re
from typing import Any, Dict, List
from uuid import UUID

from app.models.schemas import Citation

# ---------------------------------------------------------------------------
# Regex inventory
# ---------------------------------------------------------------------------

# Canonical form used in the system prompt and context blocks.
SOURCE_PATTERN = re.compile(r"\[SOURCE_(\d+)\]")

# Sloppy comma/semicolon list: [SOURCE_1, SOURCE_2, 3] or [SOURCE_1; SOURCE_2]
_SLOPPY_LIST = re.compile(
    r"\[SOURCE_\d+(?:\s*[,;]\s*\[?(?:SOURCE_)?\d+)+\s*\]"
)
# Fused-bracket form: [SOURCE_3Foo (open bracket + digits + prose, no closing ])
# The lookahead asserts the char after the digits is NOT ], ,, ;, space, digit, or [.
_FUSED_BRACKET = re.compile(r"\[SOURCE_(\d+)(?=[^\],;\s\d\[])")
# Naked SOURCE_N with no brackets at all.
# Lookbehind/lookahead guard prevents double-wrapping already-correct markers.
_NAKED = re.compile(r"(?<!\[)SOURCE_(\d+)(?!\])")

# Valid prefix of an in-progress [SOURCE_N] citation (for the stream stripper).
# Matches [, [S, [SO, …, [SOURCE_, [SOURCE_1, [SOURCE_12, etc.
_CITATION_PREFIX = re.compile(
    r"^\[(?:S(?:O(?:U(?:R(?:C(?:E(?:_\d*)?)?)?)?)?)?)?$"
)
# Dangling partial marker at end of a buffer (no closing ]) — discarded on flush.
_DANGLING_PARTIAL = re.compile(r"\[SOURCE_\d*$")

PREVIEW_LEN = 200


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _expand_sloppy(match: re.Match) -> str:  # type: ignore[type-arg]
    ids = re.findall(r"\d+", match.group(0))
    return "".join(f"[SOURCE_{i}]" for i in ids)


def normalize_citation_markers(text: str) -> str:
    """Rewrite all malformed LLM citation variants to canonical [SOURCE_N] form.

    Handles the four patterns the LLM produces despite the system prompt:
      - [SOURCE_1, SOURCE_2, 3]  sloppy comma/semicolon list
      - [SOURCE_3Foo             open bracket fused with prose, no closing ]
      - SOURCE_3                 completely naked, no brackets
      - [SOURCE_1][SOURCE_2]     canonical (left unchanged)
    """
    text = _SLOPPY_LIST.sub(_expand_sloppy, text)
    text = _FUSED_BRACKET.sub(r"[SOURCE_\1]", text)
    text = _NAKED.sub(r"[SOURCE_\1]", text)
    return text


def strip_citation_markers(text: str) -> str:
    """Remove every citation marker from *text* (used when include_sources=False)."""
    return SOURCE_PATTERN.sub("", normalize_citation_markers(text))


# ---------------------------------------------------------------------------
# Streaming citation stripper
# ---------------------------------------------------------------------------

class CitationStreamStripper:
    """Buffer-based filter for token streams when include_sources=False.

    Holds back text once '[' is seen; discards the buffer when a complete
    [SOURCE_N] marker is confirmed, flushes it once the buffered prefix can
    no longer be a citation.
    """

    # [SOURCE_999] is 12 chars; hold up to 20 to be safe.
    _MAX_HOLD = 20

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, token: str) -> str:
        """Ingest *token*; return text that is safe to emit downstream."""
        self._buf += token
        out: list[str] = []

        while self._buf:
            # Strip any complete citation markers first.
            new_buf, n = SOURCE_PATTERN.subn("", self._buf)
            if n:
                self._buf = new_buf
                continue

            # Find the leftmost '[' that might open a citation.
            idx = self._buf.find("[")
            if idx == -1:
                out.append(self._buf)
                self._buf = ""
                break

            # Emit everything before '['.
            if idx > 0:
                out.append(self._buf[:idx])
                self._buf = self._buf[idx:]

            # self._buf now starts with '['.
            if _CITATION_PREFIX.match(self._buf):
                if len(self._buf) >= self._MAX_HOLD:
                    # Too long to be a valid citation — flush.
                    out.append(self._buf)
                    self._buf = ""
                # Otherwise keep buffering.
                break
            else:
                out.append(self._buf)
                self._buf = ""
                break

        return "".join(out)

    def flush(self) -> str:
        """Drain the buffer at end-of-stream; strip any lingering partials."""
        result = SOURCE_PATTERN.sub("", self._buf)
        result = _DANGLING_PARTIAL.sub("", result)
        self._buf = ""
        return result


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Citation resolution
# ---------------------------------------------------------------------------

def resolve_citations(
    response_text: str,
    chunks: List[Dict[str, Any]],
    include_uncited: bool = False,
) -> List[Citation]:
    """Extract citation anchors and resolve them to chunk metadata.

    Normalises malformed LLM output before scanning so that sloppy lists,
    fused-bracket forms, and naked SOURCE_N tokens are all recognised.
    """
    normalised = normalize_citation_markers(response_text)
    cited_indices = {int(m) for m in SOURCE_PATTERN.findall(normalised)}

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
