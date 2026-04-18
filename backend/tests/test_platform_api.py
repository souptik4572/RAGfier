from __future__ import annotations

import json
import uuid
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api import platform as platform_module
from app.api import public_v1 as public_v1_module
from app.api.auth import AuthContext, get_auth_context
from app.pipeline import generator as generator_module
from app.pipeline import query_pipeline as query_pipeline_module
from app.pipeline.reranker import Reranker
from tests.fakes import FakeAsyncOpenAIClient, FakeSupabaseClient


TENANT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"


def _doc(job_id: str, knowledge_base_id: str, integration_id: str | None = None) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": TENANT_ID,
        "job_id": job_id,
        "integration_id": integration_id,
        "knowledge_base_id": knowledge_base_id,
        "content": "The liability cap shall not exceed $1,000,000 in aggregate.",
        "status": "active",
        "metadata": {
            "source": "contract.pdf",
            "document_id": job_id,
            "page_number": 5,
            "bounding_boxes": [[72, 340, 540, 380]],
            "section_heading": "Section 3.2 — Liability",
            "document_title": "Master Services Agreement",
            "chunk_index": 0,
            "total_chunks": 1,
            "parser": "llamaparse",
            "chunk_strategy": "recursive_character",
            "chunk_size_tokens": 700,
            "overlap_tokens": 100,
        },
    }


@pytest.fixture
def fake_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    db.table("tenants").insert({"id": TENANT_ID, "name": "Acme", "slug": "acme"}).execute()
    db.table("tenants").insert({"id": OTHER_TENANT_ID, "name": "Other", "slug": "other"}).execute()

    def _hybrid(params):
        rows = [
            row
            for row in db.rows("documents")
            if row["tenant_id"] == params["filter_tenant_id"]
            and (
                not params.get("filter_integration_id")
                or row.get("integration_id") == params["filter_integration_id"]
            )
        ]
        return [
            {
                "id": row["id"],
                "content": row["content"],
                "metadata": row["metadata"],
                "rrf_score": 1.0 / (index + 1),
                "dense_rank": index + 1,
                "sparse_rank": index + 1,
            }
            for index, row in enumerate(rows[: params.get("match_count", 5)])
        ]

    db.register_rpc("match_documents_hybrid", _hybrid)
    return db


@pytest.fixture
def client(monkeypatch, fake_db: FakeSupabaseClient) -> TestClient:
    for mod in (platform_module, public_v1_module):
        monkeypatch.setattr(mod, "get_service_client", lambda db=fake_db: db)

    from app.api import platform_auth
    from app.pipeline import retriever_dense, retriever_sparse

    monkeypatch.setattr(platform_auth, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(retriever_dense, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(retriever_sparse, "get_service_client", lambda: fake_db)

    class _FakeBucket:
        def upload(self, **_: Any) -> None:
            return None

    class _FakeStorage:
        def from_(self, _name: str) -> _FakeBucket:
            return _FakeBucket()

    fake_db.storage = _FakeStorage()  # type: ignore[attr-defined]

    async def _noop_pipeline(**_: Any) -> None:
        return None

    monkeypatch.setattr(public_v1_module, "run_pipeline_task", _noop_pipeline)

    class _FakeEmbedder:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        async def embed_query(self, _: str) -> List[float]:
            return [0.1] * 1536

    monkeypatch.setattr(query_pipeline_module, "Embedder", _FakeEmbedder)

    fake_openai = FakeAsyncOpenAIClient(
        response_text="The liability cap is $1,000,000 [SOURCE_1]."
    )
    fake_openai.chat.completions.stream_tokens = ["The", " cap", " is", " $1M", " [SOURCE_1]"]
    monkeypatch.setattr(public_v1_module, "Generator", lambda *_, **__: generator_module.Generator(client=fake_openai))

    class _IdentityBackend:
        provider = "identity"

        def rerank(self, query, chunks, top_k):
            out = []
            for i, chunk in enumerate(chunks):
                item = dict(chunk)
                item["rerank_score"] = 0.9 - i * 0.05
                out.append(item)
            return out[:top_k]

    monkeypatch.setattr(
        query_pipeline_module,
        "Reranker",
        lambda *_, **__: Reranker(primary=_IdentityBackend(), fallback=_IdentityBackend()),
    )

    app = main_module.create_app()
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(tenant_id=TENANT_ID, user_id="user-1")
    return TestClient(app)


def _create_api_key(client: TestClient, *, return_integration_id: bool = False):
    integration_resp = client.post(
        "/platform/integrations",
        json={"name": "Production API", "environment": "production"},
        headers={"Authorization": "Bearer header.payload.sig", "X-Tenant-Id": TENANT_ID},
    )
    assert integration_resp.status_code == 201, integration_resp.text
    integration_id = integration_resp.json()["id"]
    key_resp = client.post(
        "/platform/api-keys",
        json={
            "integration_id": integration_id,
            "name": "Server key",
            "scopes": [
                "kb:write",
                "kb:read",
                "documents:write",
                "documents:read",
                "query:read",
                "connectors:write",
                "analytics:read",
            ],
        },
        headers={"Authorization": "Bearer header.payload.sig", "X-Tenant-Id": TENANT_ID},
    )
    assert key_resp.status_code == 201, key_resp.text
    secret = key_resp.json()["secret"]
    if return_integration_id:
        return secret, integration_id
    return secret


def test_platform_dashboard_creates_api_key_once_and_masks_storage(
    client: TestClient,
    fake_db: FakeSupabaseClient,
) -> None:
    secret = _create_api_key(client)
    key_row = fake_db.rows("api_keys")[0]
    assert key_row["secret_hash"] != secret
    assert secret.startswith(key_row["prefix"])
    list_resp = client.get(
        "/platform/api-keys",
        headers={"Authorization": "Bearer header.payload.sig", "X-Tenant-Id": TENANT_ID},
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["api_keys"][0]["prefix"] == key_row["prefix"]
    assert "secret" not in body["api_keys"][0]


def test_v1_query_scoped_to_tenant(
    client: TestClient,
    fake_db: FakeSupabaseClient,
) -> None:
    secret, integration_id = _create_api_key(client, return_integration_id=True)
    kb_resp = client.post(
        "/v1/knowledge-bases",
        json={"name": "Legal"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert kb_resp.status_code == 201, kb_resp.text
    kb_id = kb_resp.json()["id"]

    job_id = str(uuid.uuid4())
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": TENANT_ID,
            "integration_id": integration_id,
            "knowledge_base_id": kb_id,
            "file_name": "contract.pdf",
            "file_path": "local://contract.pdf",
            "status": "completed",
            "processed_chunks": 1,
            "total_chunks": 1,
            "created_at": "2026-04-16T10:00:00+00:00",
            "updated_at": "2026-04-16T10:01:00+00:00",
        }
    ).execute()
    fake_db.table("documents").insert(_doc(job_id, kb_id, integration_id=integration_id)).execute()

    response = client.post(
        "/v1/query",
        json={"query": "What is the liability cap?", "match_count": 2},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer"].startswith("The liability cap")
    assert body["request_id"]
    assert body["usage"]["input_tokens"] > 0
    assert fake_db.rows("request_logs")[-1]["tenant_id"] == TENANT_ID
    assert fake_db.rows("audit_logs")[-1]["action"] == "query.executed"


def test_v1_documents_connectors_usage_and_audit_roundtrip(
    client: TestClient,
    fake_db: FakeSupabaseClient,
) -> None:
    secret = _create_api_key(client)
    kb_resp = client.post(
        "/v1/knowledge-bases",
        json={"name": "Policies"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    kb_id = kb_resp.json()["id"]

    upload = client.post(
        "/v1/documents/upload",
        data={"knowledge_base_id": kb_id, "document_title": "Policy Manual"},
        files={"file": ("manual.md", b"# Manual\n\nBody", "text/markdown")},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert upload.status_code == 202, upload.text
    document_id = upload.json()["job_id"]

    list_resp = client.get("/v1/documents", headers={"Authorization": f"Bearer {secret}"})
    assert list_resp.status_code == 200
    assert list_resp.json()["documents"][0]["id"] == document_id

    detail_resp = client.get(f"/v1/documents/{document_id}", headers={"Authorization": f"Bearer {secret}"})
    assert detail_resp.status_code == 200
    assert detail_resp.json()["file_name"] == "manual.md"

    connector_resp = client.post(
        "/v1/connectors/s3",
        json={"knowledge_base_id": kb_id, "name": "S3 Sync", "bucket": "docs-bucket", "prefix": "legal/"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert connector_resp.status_code == 201, connector_resp.text
    connector_id = connector_resp.json()["id"]
    sync_resp = client.post(
        f"/v1/connectors/{connector_id}/sync",
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert sync_resp.status_code == 202
    assert fake_db.rows("connector_sync_jobs")[0]["connector_source_id"] == connector_id

    usage_resp = client.get("/v1/usage", headers={"Authorization": f"Bearer {secret}"})
    assert usage_resp.status_code == 200
    assert usage_resp.json()["buckets"]

    audit_resp = client.get("/v1/audit-logs", headers={"Authorization": f"Bearer {secret}"})
    assert audit_resp.status_code == 200
    assert any(entry["action"] == "document.uploaded" for entry in audit_resp.json()["audit_logs"])

    delete_resp = client.delete(f"/v1/documents/{document_id}", headers={"Authorization": f"Bearer {secret}"})
    assert delete_resp.status_code == 200
    assert fake_db.rows("ingestion_jobs")[0]["status"] == "deleted"


def test_v1_stream_query_emits_request_id_and_usage(
    client: TestClient,
    fake_db: FakeSupabaseClient,
) -> None:
    secret, integration_id = _create_api_key(client, return_integration_id=True)
    kb_resp = client.post(
        "/v1/knowledge-bases",
        json={"name": "Support"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    kb_id = kb_resp.json()["id"]
    job_id = str(uuid.uuid4())
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": TENANT_ID,
            "integration_id": integration_id,
            "knowledge_base_id": kb_id,
            "file_name": "support.pdf",
            "file_path": "local://support.pdf",
            "status": "completed",
            "processed_chunks": 1,
            "total_chunks": 1,
            "created_at": "2026-04-16T10:00:00+00:00",
            "updated_at": "2026-04-16T10:01:00+00:00",
        }
    ).execute()
    fake_db.table("documents").insert(_doc(job_id, kb_id, integration_id=integration_id)).execute()

    with client.stream(
        "POST",
        "/v1/query/stream",
        json={"query": "What is the liability cap?"},
        headers={"Authorization": f"Bearer {secret}"},
    ) as response:
        assert response.status_code == 200
        events: list[tuple[str, str]] = []
        current_event = None
        for raw_line in response.iter_lines():
            line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8")
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((current_event or "", line.split(":", 1)[1].strip()))

    sources_payload = json.loads(events[0][1])
    assert sources_payload["request_id"]
    done_payload = json.loads(events[-1][1])
    assert done_payload["request_id"]
    assert done_payload["usage"]["total_tokens"] > 0
