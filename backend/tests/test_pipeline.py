from __future__ import annotations

import uuid

import pytest

from app.pipeline.chunker import Chunker
from app.pipeline.embedder import Embedder
from app.pipeline.orchestrator import IngestionOrchestrator
from app.pipeline.parser import DocumentParser
from app.pipeline.upserter import DocumentUpserter
from tests.fakes import FakeOpenAIClient, FakeSupabaseClient


@pytest.mark.asyncio
async def test_orchestrator_runs_full_pipeline(tmp_path):
    md = """# Master Services Agreement

## Section 3.2 Limitation of Liability

The liability cap shall not exceed $1,000,000 in aggregate for all
claims arising under this agreement. This limitation applies to both
direct and indirect damages.

## Section 4.1 Term

This agreement commences on the effective date and continues for a
period of three years unless terminated earlier in accordance with
Section 5.
"""
    file_path = tmp_path / "msa.md"
    file_path.write_text(md, encoding="utf-8")

    tenant_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    fake_db = FakeSupabaseClient()
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "file_name": "msa.md",
            "file_path": "local://msa.md",
            "status": "pending",
            "total_chunks": 0,
            "processed_chunks": 0,
        }
    ).execute()

    parser = DocumentParser(api_key="dummy")
    chunker = Chunker(chunk_size_tokens=400, overlap_tokens=40)
    embedder = Embedder(client=FakeOpenAIClient(), batch_size=2)
    upserter = DocumentUpserter(client=fake_db)

    orchestrator = IngestionOrchestrator(
        parser=parser,
        chunker=chunker,
        embedder=embedder,
        upserter=upserter,
    )

    await orchestrator.run(
        job_id=job_id,
        tenant_id=tenant_id,
        file_path=str(file_path),
        file_name="msa.md",
        file_type="md",
        document_title="Master Services Agreement",
    )

    docs = fake_db.rows("documents")
    assert len(docs) >= 2
    for row in docs:
        assert row["tenant_id"] == tenant_id
        assert row["job_id"] == job_id
        assert len(row["embedding"]) == 1536
        meta = row["metadata"]
        assert meta["source"] == "msa.md"
        assert meta["document_id"] == job_id
        assert meta["parser"] == "llamaparse"
        assert meta["chunk_strategy"] == "recursive_character"
        assert "chunk_index" in meta and "total_chunks" in meta
        assert meta["document_title"] == "Master Services Agreement"
        # situated context prepended in content
        assert row["content"].startswith("[Document: Master Services Agreement]")

    job = fake_db.rows("ingestion_jobs")[0]
    assert job["status"] == "completed"
    assert job["total_chunks"] == len(docs)
    assert job["processed_chunks"] == len(docs)


@pytest.mark.asyncio
async def test_orchestrator_marks_failed_on_parser_error(tmp_path):
    missing = tmp_path / "missing.md"  # never created

    tenant_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    fake_db = FakeSupabaseClient()
    fake_db.table("ingestion_jobs").insert(
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "file_name": "missing.md",
            "file_path": "local://missing.md",
            "status": "pending",
            "total_chunks": 0,
            "processed_chunks": 0,
        }
    ).execute()

    orchestrator = IngestionOrchestrator(
        parser=DocumentParser(api_key="dummy"),
        chunker=Chunker(),
        embedder=Embedder(client=FakeOpenAIClient()),
        upserter=DocumentUpserter(client=fake_db),
    )

    with pytest.raises(Exception):
        await orchestrator.run(
            job_id=job_id,
            tenant_id=tenant_id,
            file_path=str(missing),
            file_name="missing.md",
            file_type="md",
        )

    job = fake_db.rows("ingestion_jobs")[0]
    assert job["status"] == "failed"
    assert job.get("error_message")
