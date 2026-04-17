from __future__ import annotations

from typing import Any, Dict, Iterable, List


def reciprocal_rank_fusion(
    dense_results: Iterable[Dict[str, Any]],
    sparse_results: Iterable[Dict[str, Any]],
    k: int = 60,
) -> List[Dict[str, Any]]:
    """Merge dense + sparse ranked lists into a single RRF-scored list.

    Each item in the inputs must have an ``id`` field. The returned list is
    sorted by descending RRF score, with ``rrf_score``, ``dense_rank``, and
    ``sparse_rank`` populated on each entry. The original metadata is
    preserved from whichever list first contributed the document.
    """
    scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}

    for rank, doc in enumerate(dense_results, start=1):
        doc_id = str(doc["id"])
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        entry = doc_map.setdefault(doc_id, dict(doc))
        entry["dense_rank"] = rank

    for rank, doc in enumerate(sparse_results, start=1):
        doc_id = str(doc["id"])
        scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
        entry = doc_map.setdefault(doc_id, dict(doc))
        entry["sparse_rank"] = rank

    fused: List[Dict[str, Any]] = []
    for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        entry = doc_map[doc_id]
        entry["rrf_score"] = score
        entry.setdefault("dense_rank", 0)
        entry.setdefault("sparse_rank", 0)
        fused.append(entry)
    return fused
