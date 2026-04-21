from __future__ import annotations

import uuid
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api import eval as eval_module
from app.api.auth import AuthContext, get_auth_context
from tests.test_eval_runner import FakeEvalClient

TENANT_ID = "33333333-3333-3333-3333-333333333333"


@pytest.fixture
def eval_client(monkeypatch) -> TestClient:
    db = FakeEvalClient()

    # Seed a run row so /eval/runs and /eval/runs/{id}/samples have data.
    run_id = str(uuid.uuid4())
    db.runs.append(
        {
            "id": run_id,
            "tenant_id": TENANT_ID,
            "dataset_version": "golden_v1.0.0",
            "trigger": "ci",
            "git_sha": "abc123",
            "git_branch": "feat/phase3",
            "status": "completed",
            "passed": True,
            "faithfulness_avg": 0.91,
            "answer_relevancy_avg": 0.87,
            "context_precision_avg": 0.82,
            "context_recall_avg": 0.79,
            "citation_coverage_avg": 0.94,
            "decline_accuracy_avg": 0.88,
            "latency_compliance_avg": 0.95,
            "total_samples": 2,
            "failed_samples": 0,
            "created_at": None,
        }
    )
    db.sample_rows.append(
        {
            "eval_run_id": run_id,
            "sample_id": "gs-001",
            "category": "exact_match",
            "user_input": "What is the liability cap?",
            "response": "$1,000,000 [SOURCE_1]",
            "faithfulness": 0.95,
            "answer_relevancy": 0.92,
            "context_precision": 0.88,
            "context_recall": 0.80,
            "citation_coverage": 1.0,
            "decline_accuracy": 1.0,
            "passed": True,
            "failure_reasons": [],
        }
    )

    monkeypatch.setattr(eval_module, "get_service_client", lambda: db)

    # Prevent the background task from trying to load real data.
    def _noop_schedule(**_: Any) -> None:
        return None

    monkeypatch.setattr(eval_module, "_schedule_task", _noop_schedule)

    app = main_module.create_app()
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(tenant_id=TENANT_ID)
    client = TestClient(app)
    client.seeded_run_id = run_id  # type: ignore[attr-defined]
    return client


def test_list_eval_runs_returns_seeded_run(eval_client: TestClient) -> None:
    response = eval_client.get("/eval/runs")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Evaluation runs retrieved successfully"
    assert len(body["runs"]) == 1
    run = body["runs"][0]
    assert run["dataset_version"] == "golden_v1.0.0"
    assert run["scores"]["faithfulness_avg"] == pytest.approx(0.91)
    assert run["passed"] is True


def test_list_samples_returns_seeded_sample(eval_client: TestClient) -> None:
    run_id = eval_client.seeded_run_id  # type: ignore[attr-defined]
    response = eval_client.get(f"/eval/runs/{run_id}/samples")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Evaluation samples retrieved successfully"
    assert len(body["samples"]) == 1
    sample = body["samples"][0]
    assert sample["sample_id"] == "gs-001"
    assert sample["scores"]["faithfulness"] == pytest.approx(0.95)


def test_list_samples_returns_404_for_unknown_run(eval_client: TestClient) -> None:
    response = eval_client.get(f"/eval/runs/{uuid.uuid4()}/samples")
    assert response.status_code == 404
    assert response.json()["message"] == "Evaluation run not found."


def test_start_eval_run_accepts_and_returns_run_id(eval_client: TestClient) -> None:
    response = eval_client.post(
        "/eval/run",
        json={"dataset_version": "golden_v1.0.0", "trigger": "manual"},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["message"] == "Evaluation pipeline started"
    assert uuid.UUID(body["eval_run_id"])
    assert body["status"] == "running"


def test_start_eval_run_rejects_missing_dataset(eval_client: TestClient) -> None:
    response = eval_client.post(
        "/eval/run",
        json={"dataset_version": "does_not_exist", "trigger": "manual"},
    )
    assert response.status_code == 404


def test_count_eval_runs_returns_tenant_scoped_total(eval_client: TestClient) -> None:
    response = eval_client.get("/eval/runs/count")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Evaluation run count retrieved successfully"
    assert body["count"] == 1
