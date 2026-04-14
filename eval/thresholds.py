from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

import yaml

from app.config import get_settings


METRIC_KEYS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "citation_coverage",
    "decline_accuracy",
    "latency_compliance",
)


@dataclass
class MetricThreshold:
    name: str
    threshold: float
    blocking: bool


@dataclass
class Thresholds:
    version: str
    metrics: Dict[str, MetricThreshold] = field(default_factory=dict)
    min_passing_rate: float = 0.80

    def get(self, name: str) -> MetricThreshold:
        return self.metrics[name]

    def blocking_metrics(self) -> list[str]:
        return [name for name, m in self.metrics.items() if m.blocking]

    def as_snapshot(self) -> dict[str, Any]:
        """Serialize the active thresholds for audit trails (eval_runs.thresholds)."""
        return {
            "version": self.version,
            "min_passing_rate": self.min_passing_rate,
            "metrics": {
                name: {"threshold": m.threshold, "blocking": m.blocking}
                for name, m in self.metrics.items()
            },
        }


def load_thresholds(path: str | Path | None = None) -> Thresholds:
    settings = get_settings()
    resolved = Path(path) if path else Path(settings.eval_thresholds_path)
    if not resolved.exists():
        return _from_settings_defaults()

    with resolved.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    metrics: Dict[str, MetricThreshold] = {}
    for name in METRIC_KEYS:
        section = raw.get(name) or {}
        metrics[name] = MetricThreshold(
            name=name,
            threshold=float(section.get("threshold", _default_for(name))),
            blocking=bool(section.get("blocking", True)),
        )
    return Thresholds(
        version=str(raw.get("version", "1.0.0")),
        metrics=metrics,
        min_passing_rate=float(raw.get("min_passing_rate", 0.80)),
    )


def _default_for(name: str) -> float:
    settings = get_settings()
    mapping = {
        "faithfulness": settings.eval_threshold_faithfulness,
        "answer_relevancy": settings.eval_threshold_answer_relevancy,
        "context_precision": settings.eval_threshold_context_precision,
        "context_recall": settings.eval_threshold_context_recall,
        "citation_coverage": settings.eval_threshold_citation_coverage,
        "decline_accuracy": settings.eval_threshold_decline_accuracy,
        "latency_compliance": settings.eval_threshold_latency_compliance,
    }
    return float(mapping[name])


def _from_settings_defaults() -> Thresholds:
    return Thresholds(
        version="defaults",
        min_passing_rate=0.80,
        metrics={name: MetricThreshold(name=name, threshold=_default_for(name), blocking=True) for name in METRIC_KEYS},
    )
