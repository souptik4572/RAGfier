from __future__ import annotations

import re

CITATION_PATTERN = re.compile(r"\[SOURCE_\d+\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_META_PREFIXES = (
    "i don't have",
    "i do not have",
    "the following sources",
    "sources:",
)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def citation_coverage_score(response: str) -> float:
    """Fraction of factual sentences in the response that carry a [SOURCE_N] anchor.

    A decline response with no factual claims scores 1.0 — there is
    nothing to cite, so coverage is vacuously perfect.
    """
    if not response or not response.strip():
        return 0.0

    sentences = _split_sentences(response)
    if not sentences:
        return 0.0

    factual = [
        s
        for s in sentences
        if len(s.split()) > 5
        and not s.lower().startswith(_META_PREFIXES)
    ]
    if not factual:
        return 1.0

    cited = [s for s in factual if CITATION_PATTERN.search(s)]
    return len(cited) / len(factual)
