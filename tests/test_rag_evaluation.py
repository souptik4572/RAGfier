"""DeepEval CI entry point.

Invoked via `deepeval test run tests/test_rag_evaluation.py` in CI.
Each parametrized test case is a single golden sample; DeepEval pass/fail
thresholds block merges when scores drop.

This module is skipped when `deepeval` is not installed (keeps the
regular unit-test suite green without pulling the heavy dependency).
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from typing import Any, List

import pytest

from eval.dataset import GoldenSample, load_golden_dataset
from eval.pipeline_adapter import run_sample_pipeline

deepeval_available = importlib.util.find_spec("deepeval") is not None
pytestmark = pytest.mark.skipif(
    not deepeval_available,
    reason="deepeval not installed — install with `pip install deepeval` to run CI gate.",
)

if deepeval_available:
    from deepeval import assert_test
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        ContextualRecallMetric,
        FaithfulnessMetric,
    )
    from deepeval.test_case import LLMTestCase


DATASET_PATH = os.getenv("EVAL_DATASET_PATH", "eval/datasets/golden_v1.0.0.json")
DEFAULT_TENANT_ID = os.getenv("EVAL_TENANT_ID", str(uuid.UUID(int=0)))


def _load_samples() -> List[GoldenSample]:
    try:
        return load_golden_dataset(DATASET_PATH).samples
    except FileNotFoundError:
        return []


def _run_pipeline(sample: GoldenSample):
    from app.models.database import get_service_client

    client = get_service_client()
    tenant_id = sample.tenant_id or DEFAULT_TENANT_ID
    return asyncio.run(
        run_sample_pipeline(query=sample.user_input, tenant_id=tenant_id, client=client)
    )


def _build_test_case(sample: GoldenSample) -> Any:
    result = _run_pipeline(sample)
    return LLMTestCase(
        input=sample.user_input,
        actual_output=result.answer,
        expected_output=sample.reference,
        retrieval_context=result.retrieved_contexts,
    )


if deepeval_available:
    _SAMPLES = _load_samples()

    @pytest.mark.parametrize("sample", _SAMPLES, ids=lambda s: s.id)
    def test_rag_faithfulness(sample: GoldenSample) -> None:
        if sample.is_unanswerable:
            pytest.skip("Faithfulness not meaningful for unanswerable samples.")
        test_case = _build_test_case(sample)
        assert_test(test_case, [FaithfulnessMetric(threshold=0.85)])

    @pytest.mark.parametrize("sample", _SAMPLES, ids=lambda s: s.id)
    def test_rag_answer_relevancy(sample: GoldenSample) -> None:
        test_case = _build_test_case(sample)
        assert_test(test_case, [AnswerRelevancyMetric(threshold=0.80)])

    @pytest.mark.parametrize("sample", _SAMPLES, ids=lambda s: s.id)
    def test_rag_context_precision(sample: GoldenSample) -> None:
        if sample.is_unanswerable:
            pytest.skip("Context precision not meaningful for unanswerable samples.")
        test_case = _build_test_case(sample)
        assert_test(test_case, [ContextualPrecisionMetric(threshold=0.75)])

    @pytest.mark.parametrize("sample", _SAMPLES, ids=lambda s: s.id)
    def test_rag_context_recall(sample: GoldenSample) -> None:
        if sample.is_unanswerable:
            pytest.skip("Context recall not meaningful for unanswerable samples.")
        test_case = _build_test_case(sample)
        assert_test(test_case, [ContextualRecallMetric(threshold=0.75)])
