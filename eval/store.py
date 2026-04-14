"""Persist evaluation results to Supabase (eval_runs + eval_sample_results)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.logger import get_logger
from eval.aggregator import RunSummary, SampleOutcome
from eval.thresholds import Thresholds

logger = get_logger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run_row(
    client: Any,
    *,
    tenant_id: str,
    dataset_version: str,
    trigger: str,
    thresholds: Thresholds,
    git_sha: Optional[str] = None,
    git_branch: Optional[str] = None,
    eval_model: Optional[str] = None,
) -> str:
    """Insert a pending eval_runs row and return its id."""
    run_id = str(uuid.uuid4())
    row = {
        "id": run_id,
        "tenant_id": tenant_id,
        "dataset_version": dataset_version,
        "trigger": trigger,
        "git_sha": git_sha,
        "git_branch": git_branch,
        "status": "running",
        "thresholds": thresholds.as_snapshot(),
        "eval_model": eval_model,
    }
    try:
        client.table("eval_runs").insert(row).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.create_failed", error=str(exc))
    return run_id


def finalize_run(
    client: Any,
    run_id: str,
    *,
    summary: RunSummary,
    duration_seconds: float,
    eval_model: Optional[str] = None,
) -> None:
    """Update the eval_runs row with aggregate scores, pass/fail, timing."""
    update: Dict[str, Any] = {
        "status": "completed",
        "faithfulness_avg": summary.averages.get("faithfulness"),
        "answer_relevancy_avg": summary.averages.get("answer_relevancy"),
        "context_precision_avg": summary.averages.get("context_precision"),
        "context_recall_avg": summary.averages.get("context_recall"),
        "citation_coverage_avg": summary.averages.get("citation_coverage"),
        "decline_accuracy_avg": summary.averages.get("decline_accuracy"),
        "latency_compliance_avg": summary.averages.get("latency_compliance"),
        "passed": summary.passed,
        "failure_reasons": summary.failure_reasons,
        "total_samples": summary.total_samples,
        "failed_samples": summary.failed_samples,
        "duration_seconds": duration_seconds,
    }
    if eval_model:
        update["eval_model"] = eval_model
    try:
        client.table("eval_runs").update(update).eq("id", run_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.finalize_failed", error=str(exc), run_id=run_id)


def mark_run_failed(
    client: Any, run_id: str, *, error: str, duration_seconds: float
) -> None:
    try:
        client.table("eval_runs").update(
            {
                "status": "failed",
                "passed": False,
                "failure_reasons": [{"metric": "runner", "reason": error}],
                "duration_seconds": duration_seconds,
            }
        ).eq("id", run_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.mark_failed", error=str(exc), run_id=run_id)


def store_sample_results(
    client: Any,
    run_id: str,
    outcomes: List[SampleOutcome],
) -> None:
    rows = [_sample_to_row(run_id, o) for o in outcomes]
    if not rows:
        return
    try:
        client.table("eval_sample_results").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.samples_failed", error=str(exc), run_id=run_id)


def _sample_to_row(run_id: str, outcome: SampleOutcome) -> Dict[str, Any]:
    return {
        "eval_run_id": run_id,
        "sample_id": outcome.sample_id,
        "category": outcome.category,
        "user_input": outcome.user_input,
        "response": outcome.response,
        "retrieved_contexts": outcome.retrieved_contexts,
        "reference": outcome.reference,
        "faithfulness": outcome.scores.get("faithfulness"),
        "answer_relevancy": outcome.scores.get("answer_relevancy"),
        "context_precision": outcome.scores.get("context_precision"),
        "context_recall": outcome.scores.get("context_recall"),
        "citation_coverage": outcome.scores.get("citation_coverage"),
        "decline_accuracy": outcome.scores.get("decline_accuracy"),
        "latency_ms": outcome.latency_ms,
        "passed": outcome.passed,
        "failure_reasons": outcome.failure_reasons,
        "num_chunks_retrieved": outcome.num_chunks_retrieved,
        "top_rerank_score": outcome.top_rerank_score,
        "model_used": outcome.model_used,
        "prompt_version": outcome.prompt_version,
    }


def list_runs(
    client: Any, tenant_id: str, *, limit: int = 20
) -> List[Dict[str, Any]]:
    try:
        response = (
            client.table("eval_runs")
            .select("*")
            .eq("tenant_id", tenant_id)
            .limit(limit)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.list_runs_failed", error=str(exc))
        return []
    return list(response.data or [])


def list_samples_for_run(
    client: Any, run_id: str
) -> List[Dict[str, Any]]:
    try:
        response = (
            client.table("eval_sample_results")
            .select("*")
            .eq("eval_run_id", run_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.list_samples_failed", error=str(exc))
        return []
    return list(response.data or [])


def fetch_run(client: Any, run_id: str) -> Optional[Dict[str, Any]]:
    try:
        response = (
            client.table("eval_runs").select("*").eq("id", run_id).limit(1).execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store.fetch_run_failed", error=str(exc))
        return None
    rows = response.data or []
    return rows[0] if rows else None
