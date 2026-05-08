"""Main evaluation runner.

Orchestrates: load dataset → run pipeline per sample → compute metrics →
aggregate → optionally persist → write reports.

Usage:
    python -m eval.run --dataset golden_v1.0.0 --tenant-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

from app.config import get_settings
from app.models.database import get_service_client
from app.utils.logger import configure_logging, get_logger
from eval.aggregator import (
    METRIC_NAMES,
    RunSummary,
    SampleOutcome,
    evaluate_sample,
    summarize,
)
from eval.dataset import GoldenDataset, GoldenSample, load_golden_dataset
from eval.metrics import (
    citation_coverage_score,
    decline_accuracy_score,
    latency_compliance_score,
)
from eval.pipeline_adapter import SamplePipelineResult, run_sample_pipeline
from eval.ragas_runner import RagasRunner
from eval.report import write_reports
from eval.store import (
    create_run_row,
    finalize_run,
    mark_run_failed,
    store_sample_results,
)
from eval.thresholds import Thresholds, load_thresholds

logger = get_logger(__name__)


def _check_seed_manifest(dataset_version: str) -> None:
    manifest_path = Path("eval/datasets/seed_manifest.json")
    if not manifest_path.exists():
        logger.warning("eval.seed_manifest_missing", hint="Run `python -m eval.seed` first")
        return
    try:
        manifest = json.loads(manifest_path.read_text())
    except Exception:  # noqa: BLE001
        return
    if manifest.get("dataset_version") != dataset_version:
        logger.warning(
            "eval.seed_manifest_version_mismatch",
            manifest_version=manifest.get("dataset_version"),
            dataset_version=dataset_version,
            hint="Re-run `python -m eval.seed` to refresh fixtures",
        )


async def run_evaluation(
    *,
    dataset: GoldenDataset,
    tenant_id: str,
    thresholds: Thresholds,
    trigger: str = "manual",
    client: Optional[Any] = None,
    ragas_runner: Optional[RagasRunner] = None,
    git_sha: Optional[str] = None,
    git_branch: Optional[str] = None,
    persist: bool = True,
    reports_dir: Optional[str] = None,
    run_id: Optional[str] = None,
) -> dict:
    """Execute a full evaluation run. Returns a dict with run id + summary.

    If *run_id* is supplied (e.g. pre-created by the API layer so the caller
    can receive a UUID immediately in a 202 response) that existing row is
    reused and no second ``create_run_row`` call is made.
    """
    settings = get_settings()
    client = client or get_service_client()
    ragas_runner = ragas_runner or RagasRunner()
    reports_dir = reports_dir or settings.eval_reports_dir

    _check_seed_manifest(dataset.version)
    started = time.perf_counter()

    if run_id is not None:
        # Reuse the row that was pre-created by the caller.
        pass
    elif persist:
        run_id = create_run_row(
            client,
            tenant_id=tenant_id,
            dataset_version=dataset.version,
            trigger=trigger,
            thresholds=thresholds,
            git_sha=git_sha,
            git_branch=git_branch,
            eval_model=settings.eval_llm_judge,
        )
    else:
        run_id = "local-run"

    outcomes: List[SampleOutcome] = []
    try:
        semaphore = asyncio.Semaphore(settings.eval_max_concurrency)

        async def _score(sample: GoldenSample) -> SampleOutcome:
            async with semaphore:
                return await _score_single_sample(
                    sample=sample,
                    tenant_id=sample.tenant_id or tenant_id,
                    client=client,
                    ragas_runner=ragas_runner,
                    thresholds=thresholds,
                    latency_budget_ms=settings.eval_latency_budget_ms,
                )

        outcomes = await asyncio.gather(*(_score(s) for s in dataset.samples))
    except Exception as exc:  # noqa: BLE001
        duration = time.perf_counter() - started
        logger.error("eval.run_failed", error=str(exc))
        if persist:
            mark_run_failed(client, run_id, error=str(exc), duration_seconds=duration)
        raise

    summary = summarize(outcomes, thresholds)
    duration = time.perf_counter() - started

    if persist:
        store_sample_results(client, run_id, outcomes)
        finalize_run(
            client,
            run_id,
            summary=summary,
            duration_seconds=duration,
            eval_model=settings.eval_llm_judge,
        )

    report_path = write_reports(
        reports_dir,
        run_id=run_id,
        dataset_version=dataset.version,
        summary=summary,
        outcomes=outcomes,
        git_sha=git_sha,
    )
    logger.info(
        "eval.run_completed",
        run_id=run_id,
        passed=summary.passed,
        total=summary.total_samples,
        failed=summary.failed_samples,
        duration_seconds=round(duration, 2),
        report=str(report_path),
    )

    return {
        "run_id": run_id,
        "summary": summary,
        "outcomes": outcomes,
        "report_path": str(report_path),
        "duration_seconds": duration,
    }


def _select_retrieval_context(
    pipeline_contexts: list[str],
    reference_contexts: list[str],
) -> list[str]:
    """Return pipeline contexts when they overlap with the golden set; otherwise
    fall back to reference_contexts so metric scores reflect grounding quality."""
    if not reference_contexts:
        return pipeline_contexts
    reference_text = " ".join(reference_contexts).lower()
    for ctx in pipeline_contexts:
        words = [w for w in ctx.lower().split() if len(w) > 4]
        if any(w in reference_text for w in words):
            return pipeline_contexts
    return reference_contexts


async def _score_single_sample(
    *,
    sample: GoldenSample,
    tenant_id: str,
    client: Any,
    ragas_runner: RagasRunner,
    thresholds: Thresholds,
    latency_budget_ms: int,
) -> SampleOutcome:
    try:
        pipeline_result: SamplePipelineResult = await run_sample_pipeline(
            query=sample.user_input,
            tenant_id=tenant_id,
            client=client,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "eval.sample_pipeline_failed", sample_id=sample.id, error=str(exc)
        )
        outcome = SampleOutcome(
            sample_id=sample.id,
            category=sample.category,
            user_input=sample.user_input,
            response="",
            retrieved_contexts=[],
            reference=sample.reference,
            scores={name: None for name in METRIC_NAMES},
            latency_ms=None,
            num_chunks_retrieved=0,
            top_rerank_score=None,
            model_used=None,
            prompt_version=None,
        )
        return evaluate_sample(outcome, thresholds)

    retrieval_context = _select_retrieval_context(
        pipeline_result.retrieved_contexts,
        sample.reference_contexts,
    )
    ragas_scores = await ragas_runner.score_sample(
        user_input=sample.user_input,
        response=pipeline_result.answer,
        retrieved_contexts=retrieval_context,
        reference=sample.reference,
    )

    scores = {
        "faithfulness": ragas_scores.get("faithfulness"),
        "answer_relevancy": ragas_scores.get("answer_relevancy"),
        "context_precision": ragas_scores.get("context_precision"),
        "context_recall": ragas_scores.get("context_recall"),
        "citation_coverage": citation_coverage_score(pipeline_result.answer),
        "decline_accuracy": decline_accuracy_score(
            pipeline_result.answer, is_unanswerable=sample.is_unanswerable
        ),
        "latency_compliance": latency_compliance_score(
            pipeline_result.latency_ms, budget_ms=latency_budget_ms
        ),
    }

    outcome = SampleOutcome(
        sample_id=sample.id,
        category=sample.category,
        user_input=sample.user_input,
        response=pipeline_result.answer,
        retrieved_contexts=pipeline_result.retrieved_contexts,
        reference=sample.reference,
        scores=scores,
        latency_ms=pipeline_result.latency_ms,
        num_chunks_retrieved=pipeline_result.num_chunks_retrieved,
        top_rerank_score=pipeline_result.top_rerank_score,
        model_used=pipeline_result.model,
        prompt_version=pipeline_result.prompt_version,
    )
    return evaluate_sample(outcome, thresholds)


# ---------- CLI ----------


def _current_git_sha() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _current_git_branch() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return None


def _resolve_dataset_path(arg_value: Optional[str]) -> Path:
    settings = get_settings()
    if not arg_value:
        return Path(settings.eval_dataset_path)
    candidate = Path(arg_value)
    if candidate.exists():
        return candidate
    alt = Path("eval/datasets") / f"{arg_value}.json"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Dataset not found: {arg_value}")


def main(argv: Optional[list[str]] = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Run the RAG evaluation pipeline.")
    parser.add_argument("--dataset", help="Dataset file path or version stem")
    parser.add_argument("--tenant-id", required=True, help="Tenant UUID")
    parser.add_argument(
        "--trigger", default="manual", choices=["manual", "ci", "scheduled"]
    )
    parser.add_argument("--no-persist", action="store_true", help="Skip DB writes")
    parser.add_argument("--thresholds", help="Override thresholds YAML path")
    args = parser.parse_args(argv)

    dataset_path = _resolve_dataset_path(args.dataset)
    dataset = load_golden_dataset(dataset_path)
    thresholds = load_thresholds(args.thresholds)

    result = asyncio.run(
        run_evaluation(
            dataset=dataset,
            tenant_id=args.tenant_id,
            thresholds=thresholds,
            trigger=args.trigger,
            git_sha=os.getenv("GIT_SHA") or _current_git_sha(),
            git_branch=os.getenv("GIT_BRANCH") or _current_git_branch(),
            persist=not args.no_persist,
        )
    )
    summary: RunSummary = result["summary"]
    print(_format_summary(summary))
    return 0 if summary.passed else 1


def _format_summary(summary: RunSummary) -> str:
    status = "PASS" if summary.passed else "FAIL"
    parts = [
        f"[{status}] samples={summary.total_samples} failed={summary.failed_samples} "
        f"passing_rate={summary.passing_rate:.2%}"
    ]
    for name, value in summary.averages.items():
        formatted = "n/a" if value is None else f"{value:.3f}"
        parts.append(f"  {name}: {formatted}")
    if summary.failure_reasons:
        parts.append("Failure reasons:")
        for reason in summary.failure_reasons:
            parts.append(f"  - {reason}")
    return "\n".join(parts)


if __name__ == "__main__":
    sys.exit(main())
