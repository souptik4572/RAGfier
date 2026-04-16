"""Generate Markdown + JSON reports for evaluation runs."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from eval.aggregator import RunSummary, SampleOutcome


def write_reports(
    reports_dir: str | Path,
    *,
    run_id: str,
    dataset_version: str,
    summary: RunSummary,
    outcomes: List[SampleOutcome],
    git_sha: Optional[str] = None,
) -> Path:
    """Write JSON + Markdown reports for a run. Returns the JSON path."""
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / f"{run_id}.json"
    md_path = directory / f"{run_id}.md"

    payload = {
        "run_id": run_id,
        "dataset_version": dataset_version,
        "git_sha": git_sha,
        "summary": {
            "passed": summary.passed,
            "total_samples": summary.total_samples,
            "failed_samples": summary.failed_samples,
            "passing_rate": summary.passing_rate,
            "averages": summary.averages,
            "failure_reasons": summary.failure_reasons,
        },
        "samples": [asdict(o) for o in outcomes],
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_render_markdown(payload, outcomes), encoding="utf-8")
    return json_path


def _render_markdown(payload: dict, outcomes: List[SampleOutcome]) -> str:
    summary = payload["summary"]
    status = "PASS" if summary["passed"] else "FAIL"
    lines = [
        f"# RAG Evaluation Report — {status}",
        "",
        f"- **Run ID**: `{payload['run_id']}`",
        f"- **Dataset**: `{payload['dataset_version']}`",
        f"- **Git SHA**: `{payload.get('git_sha') or 'n/a'}`",
        f"- **Samples**: {summary['total_samples']} total, {summary['failed_samples']} failed",
        f"- **Passing rate**: {summary['passing_rate']:.2%}",
        "",
        "## Averages",
        "",
        "| Metric | Score |",
        "|---|---|",
    ]
    for name, value in summary["averages"].items():
        formatted = "n/a" if value is None else f"{value:.3f}"
        lines.append(f"| {name} | {formatted} |")

    if summary["failure_reasons"]:
        lines.extend(["", "## Failure Reasons", ""])
        for reason in summary["failure_reasons"]:
            lines.append(f"- `{reason}`")

    lines.extend(["", "## Failing Samples", ""])
    any_failed = False
    for outcome in outcomes:
        if outcome.passed:
            continue
        any_failed = True
        lines.append(
            f"- **{outcome.sample_id}** ({outcome.category}): "
            + ", ".join(outcome.failure_reasons)
        )
    if not any_failed:
        lines.append("- None")

    return "\n".join(lines) + "\n"
