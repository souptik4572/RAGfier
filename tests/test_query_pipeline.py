from __future__ import annotations

import json
import uuid
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.api import health as health_module
from app.api import ingest as ingest_module
from app.api import prompts as prompts_module
from app.api import query as query_module
from app.api import query_stream as query_stream_module
from app.api import status as status_module
from app.api.auth import AuthContext, get_auth_context
from app.pipeline import generator as generator_module
from app.pipeline import query_pipeline as query_pipeline_module
from app.pipeline.reranker import Reranker
from tests.fakes import FakeAsyncOpenAIClient, FakeSupabaseClient


TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _doc(content: str, idx: int = 0) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "content": content,
        "metadata": {
            "source": "contract.pdf",
            "document_id": "doc-1",
            "page_number": idx + 5,
            "bounding_boxes": [[72, 340, 540, 380]],
            "section_heading": f"Section 3.{idx + 2} — Limitation of Liability",
            "document_title": "Master Services Agreement",
            "chunk_index": idx,
            "total_chunks": 2,
            "parser": "llamaparse",
            "chunk_strategy": "recursive_character",
            "chunk_size_tokens": 700,
            "overlap_tokens": 100,
        },
    }


@pytest.fixture
def fake_db() -> FakeSupabaseClient:
    db = FakeSupabaseClient()
    # Seed two tenant-scoped docs.
    for i, text in enumerate(
        [
            "The liability cap shall not exceed $1,000,000 in aggregate.",
            "Section 3.2 governs all liability limitations.",
        ]
    ):
        doc = _doc(text, idx=i)
        doc["tenant_id"] = TENANT_ID
        db.table("documents").insert(doc).execute()

    def _hybrid(params):
        rows = [r for r in db.rows("documents") if r["tenant_id"] == params["filter_tenant_id"]]
        out = []
        for rank, row in enumerate(rows[: params.get("match_count", 5)], start=1):
            out.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "rrf_score": 0.05 / rank,
                    "dense_rank": rank,
                    "sparse_rank": rank,
                }
            )
        return out

    db.register_rpc("match_documents_hybrid", _hybrid)
    return db


@pytest.fixture
def client(monkeypatch, fake_db) -> TestClient:
    for mod in (
        ingest_module,
        status_module,
        query_module,
        query_stream_module,
        health_module,
        prompts_module,
    ):
        monkeypatch.setattr(mod, "get_service_client", lambda db=fake_db: db)

    # Also patch retrievers and prompt loader call sites that import
    # get_service_client internally.
    from app.pipeline import retriever_dense, retriever_sparse

    monkeypatch.setattr(retriever_dense, "get_service_client", lambda: fake_db)
    monkeypatch.setattr(retriever_sparse, "get_service_client", lambda: fake_db)

    # Storage stubs for /ingest.
    class _FakeBucket:
        def upload(self, **_: Any) -> None:
            return None

    class _FakeStorage:
        def from_(self, _name: str) -> _FakeBucket:
            return _FakeBucket()

    fake_db.storage = _FakeStorage()  # type: ignore[attr-defined]

    # Fake embedder: deterministic, never calls OpenAI.
    class _FakeEmbedder:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        async def embed_query(self, _: str) -> List[float]:
            return [0.1] * 1536

        async def embed_texts(self, texts: List[str]) -> List[List[float]]:
            return [[0.1] * 1536 for _ in texts]

    monkeypatch.setattr(query_pipeline_module, "Embedder", _FakeEmbedder)

    # Fake OpenAI client for Generator (non-streaming + streaming).
    fake_openai = FakeAsyncOpenAIClient(
        response_text="The liability cap is $1,000,000 [SOURCE_1]."
    )
    fake_openai.chat.completions.stream_tokens = [
        "The",
        " cap",
        " is",
        " $1M",
        " [SOURCE_1]",
    ]

    def _make_generator(*_: Any, **__: Any):
        return generator_module.Generator(client=fake_openai)

    monkeypatch.setattr(query_module, "Generator", _make_generator)
    monkeypatch.setattr(query_stream_module, "Generator", _make_generator)

    # Skip reranking API calls: wire a Reranker with a trivial stub backend.
    class _IdentityBackend:
        provider = "identity"

        def rerank(self, query, chunks, top_k):
            out = []
            for i, c in enumerate(chunks):
                entry = dict(c)
                entry["rerank_score"] = 0.9 - i * 0.05
                out.append(entry)
            return out[:top_k]

    def _make_reranker(*_: Any, **__: Any) -> Reranker:
        return Reranker(primary=_IdentityBackend(), fallback=_IdentityBackend())

    monkeypatch.setattr(query_pipeline_module, "Reranker", _make_reranker)

    app = main_module.create_app()
    app.dependency_overrides[get_auth_context] = lambda: AuthContext(tenant_id=TENANT_ID)
    return TestClient(app)


def test_query_returns_answer_and_resolved_citations(client: TestClient) -> None:
    response = client.post(
        "/query",
        json={"query": "What is the liability cap?", "match_count": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Query completed successfully"
    assert body["query"] == "What is the liability cap?"
    assert body["answer"].startswith("The liability cap is $1,000,000")
    assert body["declined"] is False
    assert len(body["citations"]) == 1
    citation = body["citations"][0]
    assert citation["source_id"] == "SOURCE_1"
    assert citation["metadata"]["source"] == "contract.pdf"
    assert citation["rerank_score"] == pytest.approx(0.9)
    meta = body["retrieval_metadata"]
    assert meta["rrf_candidates"] == 2
    assert meta["reranked_top_k"] == 2
    assert meta["latency_ms"]["total"] >= 0


def test_query_declines_when_retrieval_empty(monkeypatch, client: TestClient) -> None:
    # Rebuild the hybrid RPC to return nothing.
    from app.pipeline import retriever_dense, retriever_sparse  # noqa: F401

    db: FakeSupabaseClient = query_module.get_service_client()
    db.register_rpc("match_documents_hybrid", lambda params: [])

    response = client.post(
        "/query",
        json={"query": "totally unrelated", "match_count": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Query declined due to insufficient context"
    assert body["declined"] is True
    assert body["answer"].startswith("I don't have enough information")
    assert body["citations"] == []


def test_query_falls_back_to_dense_when_hybrid_rpc_missing(client: TestClient) -> None:
    db: FakeSupabaseClient = query_module.get_service_client()

    def _missing_hybrid(_params):
        raise RuntimeError(
            "{'message': 'Could not find the function public.match_documents_hybrid(...) in the schema cache', 'code': 'PGRST202'}"
        )

    def _dense(params):
        rows = [r for r in db.rows("documents") if r["tenant_id"] == params["filter_tenant_id"]]
        out = []
        for rank, row in enumerate(rows[: params.get("match_count", 5)], start=1):
            out.append(
                {
                    "id": row["id"],
                    "content": row["content"],
                    "metadata": row["metadata"],
                    "similarity": 1.0 / rank,
                }
            )
        return out

    db.register_rpc("match_documents_hybrid", _missing_hybrid)
    db.register_rpc("match_documents", _dense)

    response = client.post(
        "/query",
        json={"query": "What is the liability cap?", "match_count": 2},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Query completed successfully"
    assert body["declined"] is False
    assert body["answer"].startswith("The liability cap")
    assert body["retrieval_metadata"]["dense_results"] >= 1


def test_query_stream_emits_sources_then_tokens_then_done(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/query/stream",
        json={"query": "What is the liability cap?", "match_count": 2},
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
                data = line.split(":", 1)[1].strip()
                events.append((current_event or "", data))

    event_types = [e[0] for e in events]
    assert event_types[0] == "sources"
    assert "token" in event_types
    assert event_types[-1] == "done"

    sources_data = json.loads(events[0][1])
    assert sources_data["message"] == "Sources prepared successfully"
    assert len(sources_data["citations"]) == 2

    token_texts = [data for ev, data in events if ev == "token"]
    # sse-starlette strips leading spaces in data; ensure we got non-empty tokens.
    assert any("cap" in t for t in token_texts)

    done_payload = json.loads(events[-1][1])
    assert done_payload["message"] == "Query stream completed successfully"
    assert done_payload["declined"] is False
    assert "retrieval_metadata" in done_payload


def test_prompts_list_and_create_roundtrip(client: TestClient) -> None:
    create_resp = client.post(
        "/prompts",
        json={
            "name": "rag_generation_v1",
            "system_prompt": "tenant override",
            "user_prompt_template": "CTX {context} Q {query}",
            "metadata": {"model": "gpt-4o-mini"},
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "rag_generation_v1"
    assert created["is_active"] is True
    assert created["message"] == "Prompt created successfully"

    list_resp = client.get("/prompts")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["message"] == "Prompts retrieved successfully"
    prompts = list_body["prompts"]
    assert any(p["name"] == "rag_generation_v1" for p in prompts)
