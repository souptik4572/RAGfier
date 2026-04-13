from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api import ingest as ingest_module
from app.api import query as query_module
from app.api import status as status_module
from app.api.auth import AuthContext, get_auth_context
from tests.fakes import FakeOpenAIClient, FakeSupabaseClient


TENANT_ID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def fake_db() -> FakeSupabaseClient:
    return FakeSupabaseClient()


@pytest.fixture
def client(monkeypatch, fake_db) -> TestClient:
    # Stub the service client used by ingest/status/query/health.
    monkeypatch.setattr(ingest_module, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(status_module, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(query_module, "get_service_client", lambda: fake_db)

    # Health uses its own import path.
    from app.api import health as health_module

    monkeypatch.setattr(health_module, "get_service_client", lambda: fake_db)

    # Storage uploads go to a stub that mimics supabase.storage.
    class _FakeBucket:
        def upload(self, **_: Any) -> None:
            return None

    class _FakeStorage:
        def from_(self, _name: str) -> _FakeBucket:
            return _FakeBucket()

    fake_db.storage = _FakeStorage()  # type: ignore[attr-defined]

    # Swap the embedder used by /query with a fake.
    class _FakeEmbedder:
        def __init__(self, *_: Any, **__: Any) -> None:
            self._client = FakeOpenAIClient()

        async def embed_query(self, _: str) -> list[float]:
            return [0.1] * 1536

    monkeypatch.setattr(query_module, "Embedder", _FakeEmbedder)

    # Register a match_documents rpc handler.
    def _match_documents(params):
        rows = fake_db.rows("documents")
        tenant = params.get("filter_tenant_id")
        count = params.get("match_count", 5)
        filtered = [r for r in rows if r["tenant_id"] == tenant]
        out = []
        for row in filtered[:count]:
            out.append(
                {
                    "id": row.get("id", str(uuid.uuid4())),
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "similarity": 0.9,
                }
            )
        return out

    fake_db.register_rpc("match_documents", _match_documents)

    # Stub background pipeline so /ingest returns immediately.
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
    assert "version" in body


def test_ingest_rejects_unsupported_type(client: TestClient) -> None:
    response = client.post(
        "/ingest",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422


def test_ingest_creates_job(client: TestClient, fake_db: FakeSupabaseClient) -> None:
    response = client.post(
        "/ingest",
        files={"file": ("note.md", b"# Hi\n\nbody", "text/markdown")},
        data={"document_title": "Note"},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
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


def test_query_returns_results(client: TestClient, fake_db: FakeSupabaseClient) -> None:
    doc_id = str(uuid.uuid4())
    fake_db.table("documents").insert(
        {
            "id": doc_id,
            "tenant_id": TENANT_ID,
            "content": "[Document: MSA]\n[Section: 3.2]\nThe cap is $1M.",
            "metadata": {
                "source": "msa.pdf",
                "document_id": "doc-1",
                "page_number": 5,
                "bounding_boxes": [[72, 340, 540, 380]],
                "section_heading": "3.2 Limitation of Liability",
                "document_title": "MSA",
                "chunk_index": 0,
                "total_chunks": 1,
                "parser": "llamaparse",
                "chunk_strategy": "recursive_character",
                "chunk_size_tokens": 12,
                "overlap_tokens": 100,
            },
        }
    ).execute()

    response = client.post(
        "/query",
        json={"query": "what is the liability cap?", "match_count": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "what is the liability cap?"
    assert len(body["results"]) == 1
    result = body["results"][0]
    assert result["metadata"]["source"] == "msa.pdf"
    assert result["similarity"] == pytest.approx(0.9)
