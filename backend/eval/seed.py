"""Golden dataset seeder — seeds reference_contexts into the eval tenant's vector store.

Run once before the first eval run on a fresh environment:
    python -m eval.seed --dataset golden_v1.0.0 --tenant-id <eval-tenant-uuid> [--reset]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import get_logger
from eval.dataset import GoldenDataset, load_golden_dataset
from app.pipeline.embedder import Embedder
from app.models.database import get_service_client

log = get_logger(__name__)

MANIFEST_PATH = "eval/datasets/seed_manifest.json"
INTEGRATION_ID = "eval-fixtures"


@dataclass
class SeedResult:
    dataset_version: str
    tenant_id: str
    chunk_count: int
    skipped_count: int
    seeded_at: str


def _chunk_id(tenant_id: str, content: str) -> str:
    """Deterministic, stable ID: sha256(tenant_id + content)."""
    return hashlib.sha256(f"{tenant_id}{content}".encode()).hexdigest()


def _collect_contexts(dataset: GoldenDataset) -> dict[str, dict]:
    """Collect unique reference_contexts across all samples, keyed by content hash."""
    unique: dict[str, dict] = {}
    for sample in dataset.samples:
        for ctx in (sample.reference_contexts or []):
            h = hashlib.sha256(ctx.encode()).hexdigest()
            if h not in unique:
                unique[h] = {"content": ctx, "sample_id": sample.id}
    return unique


async def _embed_and_upsert(
    contexts: dict[str, dict],
    tenant_id: str,
    client: Any,
    embedder: Embedder,
    dataset_version: str,
) -> tuple[int, int]:
    """Embed each unique context and upsert into document_chunks. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    for ctx_hash, ctx_data in contexts.items():
        try:
            embedding = await embedder.embed_query(ctx_data["content"])
            chunk_id = _chunk_id(tenant_id, ctx_data["content"])
            row = {
                "id": chunk_id,
                "content": ctx_data["content"],
                "tenant_id": tenant_id,
                "integration_id": INTEGRATION_ID,
                "embedding": embedding,
                "metadata": {
                    "sample_id": ctx_data["sample_id"],
                    "dataset_version": dataset_version,
                },
            }
            result = (
                client.table("document_chunks")
                .upsert(row, on_conflict="id")
                .execute()
            )
            if result.data:
                inserted += 1
            else:
                skipped += 1
        except Exception as exc:
            log.warning("seed.embed_failed", content_hash=ctx_hash, error=str(exc))
            skipped += 1
    return inserted, skipped


def _write_manifest(result: SeedResult, manifest_path: str = MANIFEST_PATH) -> None:
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(
            {
                "dataset_version": result.dataset_version,
                "seeded_at": result.seeded_at,
                "tenant_id": result.tenant_id,
                "chunk_count": result.chunk_count,
            },
            f,
            indent=2,
        )


async def _seed_fixtures_async(
    dataset: GoldenDataset,
    tenant_id: str,
    client: Any,
    embedder: Embedder,
    reset: bool = False,
) -> SeedResult:
    if reset:
        log.info("seed.reset", tenant_id=tenant_id)
        client.table("document_chunks").delete().eq("tenant_id", tenant_id).eq(
            "integration_id", INTEGRATION_ID
        ).execute()
    contexts = _collect_contexts(dataset)
    log.info("seed.start", total_unique_contexts=len(contexts), tenant_id=tenant_id)
    inserted, skipped = await _embed_and_upsert(
        contexts, tenant_id, client, embedder, dataset.version
    )
    result = SeedResult(
        dataset_version=dataset.version,
        tenant_id=tenant_id,
        chunk_count=inserted,
        skipped_count=skipped,
        seeded_at=datetime.now(timezone.utc).isoformat(),
    )
    _write_manifest(result)
    log.info(
        "seed.done",
        inserted=inserted,
        skipped=skipped,
        dataset_version=dataset.version,
    )
    return result


def seed_fixtures(
    dataset: GoldenDataset,
    tenant_id: str,
    client: Any,
    embedder: Embedder | None = None,
    reset: bool = False,
) -> SeedResult:
    if embedder is None:
        embedder = Embedder()
    return asyncio.run(
        _seed_fixtures_async(dataset, tenant_id, client, embedder, reset=reset)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed golden dataset fixtures into vector store")
    parser.add_argument("--dataset", default="golden_v1.0.0", help="Dataset name (without .json)")
    parser.add_argument("--tenant-id", required=True, dest="tenant_id")
    parser.add_argument("--reset", action="store_true", help="Clear existing eval-fixtures before seeding")
    args = parser.parse_args(argv)

    dataset_path = f"eval/datasets/{args.dataset}.json"
    try:
        dataset = load_golden_dataset(dataset_path)
    except FileNotFoundError:
        log.error("seed.dataset_not_found", path=dataset_path)
        return 1

    client = get_service_client()
    try:
        result = seed_fixtures(dataset, args.tenant_id, client, reset=args.reset)
    except Exception as exc:
        log.error("seed.failed", error=str(exc))
        return 1

    print(f"Seeded {result.chunk_count} chunks ({result.skipped_count} skipped) for dataset {result.dataset_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
