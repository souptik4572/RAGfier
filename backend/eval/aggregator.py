"""Aggregate per-sample scores into run-level verdicts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eval.thresholds import Thresholds

METRIC_NAMES = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "citation_coverage",
    "decline_accuracy",
    "latency_compliance",
)


@dataclass
class SampleOutcome:
    sample_id: str
    category: Optional[str]
    user_input: str
    response: str
    retrieved_contexts: List[str]
    reference: Optional[str]
    scores: Dict[str, Optional[float]]
    latency_ms: Optional[float]
    num_chunks_retrieved: int
    top_rerank_score: Optional[float]
    model_used: Optional[str]
    prompt_version: Optional[str]
    passed: bool = False
    failure_reasons: List[str] = field(default_factory=list)


@dataclass
class RunSummary:
    averages: Dict[str, Optional[float]]
    passed: bool
    failure_reasons: List[Dict[str, Any]]
    total_samples: int
    failed_samples: int
    passing_rate: float


def evaluate_sample(
    outcome: SampleOutcome, thresholds: Thresholds
) -> SampleOutcome:
    """Mark per-sample pass/fail against the blocking thresholds."""
    reasons: List[str] = []
    for name in thresholds.blocking_metrics():
        score = outcome.scores.get(name)
        threshold = thresholds.get(name).threshold
        if score is None or score < threshold:
            reasons.append(
                f"{name} {_format_score(score)} < {threshold:.2f}"
            )
    outcome.failure_reasons = reasons
    outcome.passed = not reasons
    return outcome


def summarize(
    outcomes: List[SampleOutcome], thresholds: Thresholds
) -> RunSummary:
    total = len(outcomes)
    if total == 0:
        return RunSummary(
            averages={name: None for name in METRIC_NAMES},
            passed=False,
            failure_reasons=[{"metric": "dataset", "reason": "no samples"}],
            total_samples=0,
            failed_samples=0,
            passing_rate=0.0,
        )

    averages: Dict[str, Optional[float]] = {}
    for name in METRIC_NAMES:
        valid_scores = [
            o.scores.get(name)
            for o in outcomes
            if o.scores.get(name) is not None
        ]
        averages[name] = (
            sum(valid_scores) / len(valid_scores) if valid_scores else None  # type: ignore[arg-type]
        )

    failed_samples = sum(1 for o in outcomes if not o.passed)
    passing_rate = (total - failed_samples) / total

    failure_reasons: List[Dict[str, Any]] = []
    for name in thresholds.blocking_metrics():
        avg = averages.get(name)
        threshold = thresholds.get(name).threshold
        if avg is None or avg < threshold:
            failure_reasons.append(
                {
                    "metric": name,
                    "score": avg,
                    "threshold": threshold,
                }
            )

    if passing_rate < thresholds.min_passing_rate:
        failure_reasons.append(
            {
                "metric": "passing_rate",
                "score": passing_rate,
                "threshold": thresholds.min_passing_rate,
            }
        )

    return RunSummary(
        averages=averages,
        passed=not failure_reasons,
        failure_reasons=failure_reasons,
        total_samples=total,
        failed_samples=failed_samples,
        passing_rate=passing_rate,
    )


def _format_score(value: Optional[float]) -> str:
    if value is None:
        return "null"
    return f"{value:.2f}"
