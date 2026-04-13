from __future__ import annotations

from functools import lru_cache
from typing import Iterable

import tiktoken

_ENCODING_NAME = "cl100k_base"


@lru_cache(maxsize=1)
def _get_encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding(_ENCODING_NAME)


def count_tokens(text: str) -> int:
    """Return the number of tokens in `text` using cl100k_base."""
    if not text:
        return 0
    return len(_get_encoder().encode(text))


def count_tokens_batch(texts: Iterable[str]) -> list[int]:
    encoder = _get_encoder()
    return [len(encoder.encode(t)) if t else 0 for t in texts]
