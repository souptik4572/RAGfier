"""Evaluation API — /eval/run, /eval/runs, /eval/runs/{id}/samples."""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Path as PathParam

from app.api.auth import AuthContext, get_auth_context
from app.config import get_settings
from app.models.database import get_service_client
from app.models.schemas import (
    CountResponse,
    EvalRunAcceptedResponse,
    EvalRunListResponse,
    EvalRunRequest,
    EvalRunScores,
    EvalRunSummary,
    EvalSampleListResponse,
    EvalSampleResult,
    EvalSampleScores,
)
from app.utils.api_errors import build_response, raise_api_error
from app.utils.logger import get_logger
from eval.dataset import load_golden_dataset
from eval.run import run_evaluation
from eval.store import create_run_row, fetch_run, list_runs, list_samples_for_run
from eval.thresholds import load_thresholds

logger = get_logger(__name__)

router = APIRouter(prefix="/eval", tags=["evaluation"])


def _resolve_dataset_path(version: Optional[str]) -> Path:
    settings = get_settings()
    if not version:
        return Path(settings.eval_dataset_path)
    candidate = Path(version)
    if candidate.exists():
        return candidate
    alt = Path("eval/datasets") / f"{version}.json"
    if alt.exists():
        return alt
    raise FileNotFoundError(f"Dataset not found: {version}")


async def _run_evaluation_task(
    *,
    run_id: str,
    dataset_path: Path,
    tenant_id: str,
    trigger: str,
) -> None:
    """Background task wrapper — logs failure without raising."""
    try:
        dataset = load_golden_dataset(dataset_path)
    except FileNotFoundError as exc:
        logger.error("eval.api.dataset_missing", error=str(exc))
        return
    thresholds = load_thresholds()
    client = get_service_client()
    try:
        await run_evaluation(
            dataset=dataset,
            tenant_id=tenant_id,
            thresholds=thresholds,
            trigger=trigger,
            client=client,
            persist=True,
            run_id=run_id,  # reuse the pre-created row; avoids a duplicate create
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("eval.api.run_failed", run_id=run_id, error=str(exc))


@router.post(
    "/run",
    response_model=EvalRunAcceptedResponse,
    status_code=202,
)
async def start_eval_run(
    payload: EvalRunRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_auth_context),
) -> EvalRunAcceptedResponse:
    tenant_id = str(payload.tenant_id) if payload.tenant_id else auth.tenant_id

    try:
        dataset_path = _resolve_dataset_path(payload.dataset_version)
    except FileNotFoundError as exc:
        raise_api_error(404, "eval.dataset_not_found", detail=str(exc))

    # Pre-create the run row so the caller gets a UUID immediately; the
    # background task will pick it up and transition it to completed.
    client = get_service_client()
    thresholds = load_thresholds()
    run_id = create_run_row(
        client,
        tenant_id=tenant_id,
        dataset_version=_dataset_version_from_path(dataset_path),
        trigger=payload.trigger,
        thresholds=thresholds,
        eval_model=get_settings().eval_llm_judge,
    )

    background_tasks.add_task(
        _schedule_task,
        run_id=run_id,
        dataset_path=dataset_path,
        tenant_id=tenant_id,
        trigger=payload.trigger,
    )

    return build_response(
        EvalRunAcceptedResponse,
        "eval.run_accepted",
        eval_run_id=uuid.UUID(run_id),
        status="running",
    )


def _schedule_task(
    *,
    run_id: str,
    dataset_path: Path,
    tenant_id: str,
    trigger: str,
) -> None:
    asyncio.run(
        _run_evaluation_task(
            run_id=run_id,        # forward the pre-created run_id
            dataset_path=dataset_path,
            tenant_id=tenant_id,
            trigger=trigger,
        )
    )


def _dataset_version_from_path(path: Path) -> str:
    return path.stem


@router.get("/runs", response_model=EvalRunListResponse)
async def list_eval_runs(
    auth: AuthContext = Depends(get_auth_context),
) -> EvalRunListResponse:
    client = get_service_client()
    runs = list_runs(client, auth.tenant_id, limit=50)
    summaries = [_run_to_summary(r) for r in runs]
    return build_response(EvalRunListResponse, "eval.runs_listed", runs=summaries)


@router.get("/runs/count", response_model=CountResponse)
async def count_eval_runs(
    auth: AuthContext = Depends(get_auth_context),
) -> CountResponse:
    client = get_service_client()
    rows = (
        client.table("eval_runs")
        .select("id")
        .eq("tenant_id", auth.tenant_id)
        .execute()
        .data
        or []
    )
    return build_response(CountResponse, "eval.runs_counted", count=len(rows))


@router.get(
    "/runs/{run_id}/samples",
    response_model=EvalSampleListResponse,
)
async def list_eval_samples(
    run_id: uuid.UUID = PathParam(...),
    auth: AuthContext = Depends(get_auth_context),
) -> EvalSampleListResponse:
    client = get_service_client()
    run = fetch_run(client, str(run_id))
    if not run:
        raise_api_error(404, "eval.run_not_found")
    if str(run.get("tenant_id")) != auth.tenant_id:
        raise_api_error(403, "eval.run_forbidden")

    rows = list_samples_for_run(client, str(run_id))
    samples = [_row_to_sample(r) for r in rows]
    return build_response(
        EvalSampleListResponse,
        "eval.samples_listed",
        run_id=run_id,
        samples=samples,
    )


def _run_to_summary(run: dict[str, Any]) -> EvalRunSummary:
    return EvalRunSummary(
        id=uuid.UUID(str(run["id"])),
        dataset_version=str(run.get("dataset_version", "")),
        trigger=str(run.get("trigger", "")),
        git_sha=run.get("git_sha"),
        git_branch=run.get("git_branch"),
        status=str(run.get("status", "running")),
        passed=run.get("passed"),
        scores=EvalRunScores(
            faithfulness_avg=run.get("faithfulness_avg"),
            answer_relevancy_avg=run.get("answer_relevancy_avg"),
            context_precision_avg=run.get("context_precision_avg"),
            context_recall_avg=run.get("context_recall_avg"),
            citation_coverage_avg=run.get("citation_coverage_avg"),
            decline_accuracy_avg=run.get("decline_accuracy_avg"),
            latency_compliance_avg=run.get("latency_compliance_avg"),
        ),
        total_samples=int(run.get("total_samples") or 0),
        failed_samples=int(run.get("failed_samples") or 0),
        created_at=run.get("created_at"),
    )


def _row_to_sample(row: dict[str, Any]) -> EvalSampleResult:
    return EvalSampleResult(
        sample_id=str(row.get("sample_id", "")),
        category=row.get("category"),
        user_input=str(row.get("user_input", "")),
        response=str(row.get("response", "")),
        scores=EvalSampleScores(
            faithfulness=row.get("faithfulness"),
            answer_relevancy=row.get("answer_relevancy"),
            context_precision=row.get("context_precision"),
            context_recall=row.get("context_recall"),
            citation_coverage=row.get("citation_coverage"),
            decline_accuracy=row.get("decline_accuracy"),
        ),
        passed=row.get("passed"),
        failure_reasons=row.get("failure_reasons") or [],
    )
