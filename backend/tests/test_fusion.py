from __future__ import annotations

import pytest

from app.pipeline.fusion import reciprocal_rank_fusion


def test_rrf_merges_overlapping_docs_with_highest_score() -> None:
    dense = [{"id": "a", "content": "A"}, {"id": "b", "content": "B"}]
    sparse = [{"id": "a", "content": "A"}, {"id": "c", "content": "C"}]

    fused = reciprocal_rank_fusion(dense, sparse, k=60)

    assert fused[0]["id"] == "a"
    assert fused[0]["dense_rank"] == 1
    assert fused[0]["sparse_rank"] == 1
    # A appeared in both lists, so its score is strictly greater than b or c.
    a_score = fused[0]["rrf_score"]
    for entry in fused[1:]:
        assert entry["rrf_score"] < a_score


def test_rrf_preserves_all_unique_docs() -> None:
    dense = [{"id": "a"}, {"id": "b"}]
    sparse = [{"id": "c"}, {"id": "d"}]
    fused = reciprocal_rank_fusion(dense, sparse, k=60)
    assert {e["id"] for e in fused} == {"a", "b", "c", "d"}


def test_rrf_assigns_default_ranks_when_missing() -> None:
    dense = [{"id": "a"}]
    sparse: list = []
    fused = reciprocal_rank_fusion(dense, sparse, k=60)
    assert fused[0]["dense_rank"] == 1
    assert fused[0]["sparse_rank"] == 0


def test_rrf_formula_matches_spec_example() -> None:
    # Doc ranked #1 in dense, #3 in sparse → 1/61 + 1/63
    dense = [{"id": "x"}, {"id": "y"}, {"id": "z"}]
    sparse = [{"id": "m"}, {"id": "n"}, {"id": "x"}]
    fused = reciprocal_rank_fusion(dense, sparse, k=60)
    x_entry = next(e for e in fused if e["id"] == "x")
    expected = 1 / 61 + 1 / 63
    assert abs(x_entry["rrf_score"] - expected) < 1e-9


def test_rrf_weighted_biases_semantic_over_sparse() -> None:
    # Both docs appear once in their respective list at rank 1. With a
    # 0.7 / 0.3 weighting, the dense-only doc must outrank the sparse-only.
    dense = [{"id": "sem"}]
    sparse = [{"id": "lex"}]
    fused = reciprocal_rank_fusion(
        dense,
        sparse,
        k=60,
        semantic_weight=0.7,
        full_text_weight=0.3,
    )
    sem = next(e for e in fused if e["id"] == "sem")
    lex = next(e for e in fused if e["id"] == "lex")
    assert sem["rrf_score"] == pytest.approx(0.7 / 61)
    assert lex["rrf_score"] == pytest.approx(0.3 / 61)
    assert fused[0]["id"] == "sem"


def test_rrf_weighted_preserves_backward_compat_defaults() -> None:
    # With default 1.0 / 1.0 the formula matches the unweighted expectation.
    dense = [{"id": "a"}]
    sparse = [{"id": "a"}]
    fused = reciprocal_rank_fusion(dense, sparse, k=60)
    a = next(e for e in fused if e["id"] == "a")
    assert a["rrf_score"] == pytest.approx(1 / 61 + 1 / 61)
