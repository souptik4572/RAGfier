from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class GoldenSample:
    id: str
    category: str
    user_input: str
    reference: str
    reference_contexts: List[str] = field(default_factory=list)
    difficulty: Optional[str] = None
    source_document: Optional[str] = None
    source_page: Optional[int] = None
    tags: List[str] = field(default_factory=list)
    tenant_id: Optional[str] = None

    @property
    def is_unanswerable(self) -> bool:
        # Adversarial prompts should always be declined just like unanswerable
        # ones — skip faithfulness / precision / recall for both categories.
        return self.category in ("unanswerable", "adversarial")


@dataclass
class GoldenDataset:
    version: str
    description: str
    tenant_id: Optional[str]
    samples: List[GoldenSample]

    @property
    def size(self) -> int:
        return len(self.samples)


def load_golden_dataset(path: str | Path) -> GoldenDataset:
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Golden dataset not found: {resolved}")
    with resolved.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    samples = [_parse_sample(item) for item in raw.get("samples", [])]
    return GoldenDataset(
        version=str(raw.get("version", "0.0.0")),
        description=str(raw.get("description", "")),
        tenant_id=raw.get("tenant_id"),
        samples=samples,
    )


def _parse_sample(item: dict[str, Any]) -> GoldenSample:
    return GoldenSample(
        id=str(item["id"]),
        category=str(item.get("category", "conceptual")),
        user_input=str(item["user_input"]),
        reference=str(item.get("reference", "")),
        reference_contexts=list(item.get("reference_contexts", []) or []),
        difficulty=item.get("difficulty"),
        source_document=item.get("source_document"),
        source_page=item.get("source_page"),
        tags=list(item.get("tags", []) or []),
        tenant_id=item.get("tenant_id"),
    )
