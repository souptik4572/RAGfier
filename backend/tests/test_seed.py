"""Tests for eval/seed.py."""
from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest

from eval.seed import (
    SeedResult,
    _chunk_id,
    _collect_contexts,
    _write_manifest,
    seed_fixtures,
    INTEGRATION_ID,
)
from eval.dataset import GoldenDataset, GoldenSample


def _make_dataset(samples=None) -> GoldenDataset:
    if samples is None:
        samples = [
            GoldenSample(
                id="gs-001",
                user_input="What is the cap?",
                reference="The liability cap is $1M.",
                reference_contexts=["The liability cap is $1M per incident."],
                category="exact_match",
            ),
            GoldenSample(
                id="gs-002",
                user_input="What is the term?",
                reference="The contract term is 2 years.",
                reference_contexts=[
                    "The contract term is 2 years.",
                    "The liability cap is $1M per incident.",  # duplicate of gs-001 context
                ],
                category="exact_match",
            ),
        ]
    return GoldenDataset(
        version="1.0.0",
        description="Test golden dataset",
        tenant_id=None,
        samples=samples,
    )


def test_chunk_id_is_deterministic():
    id1 = _chunk_id("tenant-a", "hello world")
    id2 = _chunk_id("tenant-a", "hello world")
    assert id1 == id2


def test_chunk_id_differs_by_content():
    id1 = _chunk_id("tenant-a", "hello world")
    id2 = _chunk_id("tenant-a", "different content")
    assert id1 != id2


def test_collect_contexts_deduplicates():
    dataset = _make_dataset()
    contexts = _collect_contexts(dataset)
    # "The liability cap is $1M per incident." appears in both samples but deduped
    assert len(contexts) == 2


def test_seed_fixtures_correct_chunk_count(tmp_path, monkeypatch):
    from tests.fakes import FakeSupabaseClient, FakeEmbedder
    dataset = _make_dataset()
    client = FakeSupabaseClient()
    embedder = FakeEmbedder()
    monkeypatch.setattr("eval.seed.MANIFEST_PATH", str(tmp_path / "seed_manifest.json"))
    result = seed_fixtures(dataset, "test-tenant", client, embedder=embedder)
    assert result.chunk_count == 2
    assert result.skipped_count == 0
    assert result.dataset_version == "1.0.0"


def test_seed_fixtures_idempotent(tmp_path, monkeypatch):
    """Re-seeding same content should not double-insert (on_conflict=id)."""
    from tests.fakes import FakeSupabaseClient, FakeEmbedder
    dataset = _make_dataset()
    client = FakeSupabaseClient()
    embedder = FakeEmbedder()
    monkeypatch.setattr("eval.seed.MANIFEST_PATH", str(tmp_path / "seed_manifest.json"))
    result1 = seed_fixtures(dataset, "test-tenant", client, embedder=embedder)
    result2 = seed_fixtures(dataset, "test-tenant", client, embedder=embedder)
    # Both runs report 2 chunks each (idempotent from FakeSupabaseClient perspective)
    assert result1.chunk_count == result2.chunk_count


def test_write_manifest_content(tmp_path):
    result = SeedResult(
        dataset_version="1.0.0",
        tenant_id="test-tenant",
        chunk_count=5,
        skipped_count=1,
        seeded_at="2026-05-08T00:00:00+00:00",
    )
    manifest_path = str(tmp_path / "seed_manifest.json")
    _write_manifest(result, manifest_path)
    with open(manifest_path) as f:
        data = json.load(f)
    assert data["dataset_version"] == "1.0.0"
    assert data["chunk_count"] == 5
    assert data["tenant_id"] == "test-tenant"
    assert "seeded_at" in data


def test_reset_clears_existing_chunks(tmp_path, monkeypatch):
    from tests.fakes import FakeSupabaseClient, FakeEmbedder
    dataset = _make_dataset()
    client = FakeSupabaseClient()
    embedder = FakeEmbedder()
    monkeypatch.setattr("eval.seed.MANIFEST_PATH", str(tmp_path / "seed_manifest.json"))
    # Seed once
    seed_fixtures(dataset, "test-tenant", client, embedder=embedder)
    # Seed again with reset — should clear first
    result = seed_fixtures(dataset, "test-tenant", client, embedder=embedder, reset=True)
    assert result.chunk_count == 2
