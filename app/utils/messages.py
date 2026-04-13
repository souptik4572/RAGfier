from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import get_settings


@lru_cache(maxsize=1)
def _load_messages() -> dict[str, Any]:
    path = Path(get_settings().messages_file)
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise RuntimeError("Message catalog must be a JSON object.")
    return data


def get_message(path: str, *, default: str | None = None) -> str:
    node: Any = _load_messages()
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            if default is not None:
                return default
            raise KeyError(f"Unknown message key: {path}")
    if not isinstance(node, str):
        if default is not None:
            return default
        raise KeyError(f"Message key does not resolve to a string: {path}")
    return node


def reset_messages() -> None:
    _load_messages.cache_clear()
