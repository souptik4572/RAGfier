"""CLI: compare two evaluation runs side-by-side.

Usage:
    python -m eval.compare --run-a <uuid> --run-b <uuid>
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional

from app.models.database import get_service_client
from app.utils.logger import configure_logging
from eval.store import fetch_run

METRICS = (
    "faithfulness_avg",
    "answer_relevancy_avg",
    "context_precision_avg",
    "context_recall_avg",
    "citation_coverage_avg",
    "decline_accuracy_avg",
    "latency_compliance_avg",
)


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "   n/a"
    return f"{float(value):6.3f}"


def _delta(a: Optional[float], b: Optional[float]) -> str:
    if a is None or b is None:
        return "     -"
    diff = float(b) - float(a)
    sign = "+" if diff >= 0 else "-"
    return f"{sign}{abs(diff):5.3f}"


def compare(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> str:
    lines = [
        f"Run A: {run_a.get('id')}  ({run_a.get('dataset_version')}, {run_a.get('trigger')}, {run_a.get('created_at')})",
        f"Run B: {run_b.get('id')}  ({run_b.get('dataset_version')}, {run_b.get('trigger')}, {run_b.get('created_at')})",
        "",
        f"{'metric':24}  {'A':>6}  {'B':>6}  {'delta':>6}",
        "-" * 48,
    ]
    for metric in METRICS:
        a = run_a.get(metric)
        b = run_b.get(metric)
        name = metric.removesuffix("_avg")
        lines.append(f"{name:24}  {_fmt(a)}  {_fmt(b)}  {_delta(a, b)}")
    lines.extend(
        [
            "",
            f"Passed: A={run_a.get('passed')}  B={run_b.get('passed')}",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Compare two evaluation runs.")
    parser.add_argument("--run-a", required=True)
    parser.add_argument("--run-b", required=True)
    args = parser.parse_args(argv)

    client = get_service_client()
    run_a = fetch_run(client, args.run_a)
    run_b = fetch_run(client, args.run_b)
    if not run_a or not run_b:
        missing = ", ".join(r for r, v in (("A", run_a), ("B", run_b)) if not v)
        print(f"error: run(s) not found: {missing}", file=sys.stderr)
        return 2

    print(compare(run_a, run_b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
