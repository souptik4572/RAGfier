from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pytest

from eval.aggregator import (
    METRIC_NAMES,
    SampleOutcome,
    evaluate_sample,
    summarize,
)
from eval.dataset import GoldenDataset, GoldenSample, load_golden_dataset
from eval.ragas_runner import RagasRunner
from eval.run import run_evaluation
from eval.thresholds import Thresholds, load_thresholds


TENANT_ID = "22222222-2222-2222-2222-222222222222"


class FakeRagasRunner(RagasRunner):
    """Deterministic runner that returns canned Ragas scores."""

    def __init__(self, scores: Dict[str, float]) -> None:
        super().__init__()
        self._initialized = True
        self._fixed_scores = scores

    async def score_sample(self, **_: Any) -> Dict[str, float]:
        return dict(self._fixed_scores)


class FakeEvalClient:
    """Captures inserts/updates on eval_runs and eval_sample_results."""

    def __init__(self) -> None:
        self.runs: List[Dict[str, Any]] = []
        self.sample_rows: List[Dict[str, Any]] = []

    def table(self, name: str) -> "FakeEvalTable":
        return FakeEvalTable(self, name)


class FakeEvalTable:
    def __init__(self, client: FakeEvalClient, name: str) -> None:
        self._client = client
        self._name = name
        self._op: str | None = None
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []

    def insert(self, payload: Any) -> "FakeEvalTable":
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload: Dict[str, Any]) -> "FakeEvalTable":
        self._op = "update"
        self._payload = payload
        return self

    def select(self, *_: Any, **__: Any) -> "FakeEvalTable":
        self._op = "select"
        return self

    def eq(self, column: str, value: Any) -> "FakeEvalTable":
        self._filters.append((column, value))
        return self

    def limit(self, _n: int) -> "FakeEvalTable":
        return self

    def execute(self) -> Any:
        class _Resp:
            def __init__(self, data: Any) -> None:
                self.data = data

        if self._op == "insert":
            payload = self._payload
            if isinstance(payload, list):
                records = payload
            else:
                records = [payload]
            target = (
                self._client.runs if self._name == "eval_runs" else self._client.sample_rows
            )
            for record in records:
                target.append(dict(record))
            return _Resp(records)

        if self._op == "update":
            target = (
                self._client.runs if self._name == "eval_runs" else self._client.sample_rows
            )
            matched = [
                row
                for row in target
                if all(row.get(col) == val for col, val in self._filters)
            ]
            for row in matched:
                row.update(self._payload)
            return _Resp(matched)

        # select
        target = (
            self._client.runs if self._name == "eval_runs" else self._client.sample_rows
        )
        matched = [
            row
            for row in target
            if all(row.get(col) == val for col, val in self._filters)
        ]
        return _Resp([dict(r) for r in matched])


class FakePipelineResult:
    def __init__(self, *, answer: str, latency_ms: int, declined: bool = False) -> None:
        self.query = "q"
        self.answer = answer
        self.retrieved_contexts = ["ctx a", "ctx b"]
        self.citations = [{"content": "ctx a"}]
        self.declined = declined
        self.latency_ms = latency_ms
        self.model = "gpt-4o"
        self.prompt_version = "rag_generation_v1:v1"
        self.num_chunks_retrieved = 2
        self.top_rerank_score = 0.88


@pytest.fixture
def thresholds() -> Thresholds:
    return load_thresholds()


@pytest.fixture
def tiny_dataset() -> GoldenDataset:
    return GoldenDataset(
        version="test_v1",
        description="unit test dataset",
        tenant_id=TENANT_ID,
        samples=[
            GoldenSample(
                id="gs-001",
                category="exact_match",
                user_input="What is the liability cap?",
                reference="$1,000,000",
                reference_contexts=["The liability cap shall not exceed $1,000,000"],
                tenant_id=TENANT_ID,
            ),
            GoldenSample(
                id="gs-002",
                category="unanswerable",
                user_input="What is the CEO's favourite colour?",
                reference="DECLINE: not in documents",
                reference_contexts=[],
                tenant_id=TENANT_ID,
            ),
        ],
    )


def _patch_pipeline(monkeypatch, results: Dict[str, FakePipelineResult]) -> None:
    async def _fake(*, query: str, **_: Any) -> FakePipelineResult:
        for sample_query, result in results.items():
            if sample_query == query:
                return result
        raise AssertionError(f"No fake result registered for: {query}")

    from eval import run as run_module

    monkeypatch.setattr(run_module, "run_sample_pipeline", _fake)


def test_passing_run_flows_through_all_stages(
    monkeypatch, tiny_dataset: GoldenDataset, thresholds: Thresholds
) -> None:
    client = FakeEvalClient()
    _patch_pipeline(
        monkeypatch,
        {
            "What is the liability cap?": FakePipelineResult(
                answer="The liability cap is $1,000,000 [SOURCE_1].", latency_ms=1200
            ),
            "What is the CEO's favourite colour?": FakePipelineResult(
                answer="I don't have enough information in the available documents.",
                latency_ms=800,
                declined=True,
            ),
        },
    )
    runner = FakeRagasRunner(
        {
            "faithfulness": 0.95,
            "answer_relevancy": 0.9,
            "context_precision": 0.85,
            "context_recall": 0.8,
        }
    )

    result = asyncio.run(
        run_evaluation(
            dataset=tiny_dataset,
            tenant_id=TENANT_ID,
            thresholds=thresholds,
            trigger="manual",
            client=client,
            ragas_runner=runner,
            reports_dir="eval/reports/tests",
        )
    )
    summary = result["summary"]
    assert summary.total_samples == 2
    assert summary.failed_samples == 0
    assert summary.passed is True
    assert summary.averages["faithfulness"] == pytest.approx(0.95)

    # Run row lifecycle: create (running) → finalize (completed).
    assert len(client.runs) == 1
    run_row = client.runs[0]
    assert run_row["status"] == "completed"
    assert run_row["passed"] is True
    assert run_row["total_samples"] == 2
    assert len(client.sample_rows) == 2

    report_path = Path(result["report_path"])
    assert report_path.exists()
    report = json.loads(report_path.read_text())
    assert report["summary"]["passed"] is True


def test_failing_run_marks_pass_false_and_records_reasons(
    monkeypatch, tiny_dataset: GoldenDataset, thresholds: Thresholds
) -> None:
    client = FakeEvalClient()
    _patch_pipeline(
        monkeypatch,
        {
            "What is the liability cap?": FakePipelineResult(
                answer="The cap is a lot of money.",  # no citation
                latency_ms=7000,  # over budget
            ),
            "What is the CEO's favourite colour?": FakePipelineResult(
                answer="The CEO's favourite colour is blue.",  # should have declined
                latency_ms=900,
            ),
        },
    )
    runner = FakeRagasRunner(
        {
            "faithfulness": 0.40,  # < 0.85
            "answer_relevancy": 0.50,  # < 0.80
            "context_precision": 0.40,  # < 0.75
            "context_recall": 0.40,  # non-blocking
        }
    )

    result = asyncio.run(
        run_evaluation(
            dataset=tiny_dataset,
            tenant_id=TENANT_ID,
            thresholds=thresholds,
            trigger="ci",
            client=client,
            ragas_runner=runner,
            reports_dir="eval/reports/tests",
        )
    )
    summary = result["summary"]
    assert summary.passed is False
    assert summary.failed_samples == 2
    metric_names = {r["metric"] for r in summary.failure_reasons}
    assert "faithfulness" in metric_names
    assert "citation_coverage" in metric_names
    assert "decline_accuracy" in metric_names

    run_row = client.runs[0]
    assert run_row["passed"] is False
    assert run_row["status"] == "completed"


def test_aggregator_passing_rate_blocks_when_too_many_fail(thresholds: Thresholds) -> None:
    outcomes = []
    for i in range(10):
        passed = i < 5  # only 50% passing
        scores = {name: 0.95 if passed else 0.1 for name in METRIC_NAMES}
        outcomes.append(
            evaluate_sample(
                SampleOutcome(
                    sample_id=f"s-{i}",
                    category="exact_match",
                    user_input=f"q{i}",
                    response="r",
                    retrieved_contexts=["c"],
                    reference="ref",
                    scores=scores,
                    latency_ms=1000,
                    num_chunks_retrieved=1,
                    top_rerank_score=0.8,
                    model_used="gpt-4o",
                    prompt_version="rag_v1",
                ),
                thresholds,
            )
        )
    summary = summarize(outcomes, thresholds)
    assert summary.passed is False
    metric_names = {r["metric"] for r in summary.failure_reasons}
    assert "passing_rate" in metric_names


def test_load_golden_dataset_parses_phase3_seed() -> None:
    dataset = load_golden_dataset("eval/datasets/golden_v1.0.0.json")
    assert dataset.version == "1.0.0"
    assert dataset.size >= 12
    categories = {s.category for s in dataset.samples}
    assert {"exact_match", "unanswerable", "adversarial"}.issubset(categories)
    assert any(s.is_unanswerable for s in dataset.samples)
