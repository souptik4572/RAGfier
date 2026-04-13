from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api import ingest as ingest_module
from app.api import status as status_module
from app.api.auth import AuthContext, get_auth_context
from tests.fakes import FakeSupabaseClient


TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def fake_db() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def client(monkeypatch, fake_db) -> TestClient:
    # Stub the service client used by ingest/status/health.
    monkeypatch.setattr(ingest_module, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(status_module, "get_service_client", lambda: fake_db)

    from app.api import health as health_module

    monkeypatch.setattr(health_module, "get_service_client", lambda: fake_db)

    class _FakeBucket:
        def upload(self, **_: Any) -> None:
            return None

    class _FakeStorage:
        def from_(self, _name: str) -> _FakeBucket:
            return _FakeBucket()

    fake_db.storage = _FakeStorage()  # type: ignore[attr-defined]

    async def _noop_pipeline(**_: Any) -> None:
        return None

    monkeypatch.setattr(ingest_module, "run_pipeline_task", _noop_pipeline)

    app = main_module.create_app()
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(tenant_id=TENANT_ID)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["message"] == "Health status retrieved successfully"
    assert "version" in body


def test_ingest_rejects_unsupported_type(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["message"] == "Unsupported file type."
    assert body["detail"]["file_type"] == "txt"


def test_ingest_creates_job(client: TestClient, fake_db: FakeSupabaseClient) -> None:
    response = client.post(
        "/ingest",
        files={"file": ("note.md", b"# Hi\n\nbody", "text/markdown")},
        data={"document_title": "Note"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["message"] == "Ingestion pipeline started"
    job_id = body["job_id"]
    assert len(fake_db.rows("ingestion_jobs")) == 1
    job = fake_db.rows("ingestion_jobs")[0]
    assert job["id"] == job_id
    assert job["tenant_id"] == TENANT_ID


def test_status_returns_job(client: TestClient, fake_db: FakeSupabaseClient) -> None:
    job_id = str(uuid.uuid4())
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": TENANT_ID,
            "file_name": "a.md",
            "file_path": "local://a.md",
            "status": "completed",
            "total_chunks": 3,
            "processed_chunks": 3,
            "error_message": None,
            "created_at": "2026-04-13T10:00:00+00:00",
            "updated_at": "2026-04-13T10:05:00+00:00",
        }
    ).execute()

    response = client.get(f"/status/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Job status retrieved successfully"
    assert body["status"] == "completed"
    assert body["total_chunks"] == 3
    assert body["processed_chunks"] == 3


def test_status_404_for_other_tenant(
    client: TestClient, fake_db: FakeSupabaseClient
) -> None:
    job_id = str(uuid.uuid4())
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": "99999999-9999-9999-9999-999999999999",
            "file_name": "x.md",
            "file_path": "local://x.md",
            "status": "pending",
            "total_chunks": 0,
            "processed_chunks": 0,
            "created_at": "2026-04-13T10:00:00+00:00",
            "updated_at": "2026-04-13T10:00:00+00:00",
        }
    ).execute()
    response = client.get(f"/status/{job_id}")
    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "Job not found for this tenant."
    assert body["detail"]["job_id"] == job_id


# The /query endpoint is exercised end-to-end in tests/test_query_pipeline.py
# after the Phase 2 hybrid-retrieval refactor.
