"""Synthetic golden-dataset generator backed by Ragas TestsetGenerator.

This CLI pulls ingested chunks for a tenant, feeds them into Ragas'
knowledge-graph-based testset generator, and writes the result to an
unreviewed draft file. Every generated sample MUST be human-reviewed
before being copied into `eval/datasets/golden_vX.Y.Z.json`.

Usage:
    python -m eval.generate --tenant-id <uuid> --size 50 \
        --output eval/datasets/synthetic_draft.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

from app.models.database import get_service_client
from app.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


def _fetch_tenant_chunks(client: Any, tenant_id: str, limit: int) -> List[dict]:
    response = (
        client.table("documents")
        .select("id,content,metadata")
        .eq("tenant_id", tenant_id)
        .limit(limit)
        .execute()
    )
    return list(response.data or [])


def generate_synthetic(
    *,
    tenant_id: str,
    size: int,
    chunk_limit: int,
    output: Path,
) -> int:
    """Generate synthetic samples and write them to `output`.

    Returns the number of samples written. Raises `RuntimeError` if
    Ragas or its dependencies aren't installed.
    """
    try:
        from ragas.testset import TestsetGenerator
        from ragas.testset.graph import KnowledgeGraph, Node, NodeType
        from ragas.testset.synthesizers import default_query_distribution
        from ragas.testset.transforms import apply_transforms, default_transforms
        from ragas.llms import llm_factory
        from ragas.embeddings import embedding_factory
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Ragas is not installed. `pip install ragas>=0.4.0` to use synthetic generation."
        ) from exc

    from app.config import get_settings

    settings = get_settings()
    client = get_service_client()
    chunks = _fetch_tenant_chunks(client, tenant_id, chunk_limit)
    if not chunks:
        raise RuntimeError(f"No ingested chunks found for tenant {tenant_id}")

    generator_llm = llm_factory(settings.eval_faithfulness_llm)
    generator_embeddings = embedding_factory()

    kg = KnowledgeGraph()
    for chunk in chunks:
        kg.nodes.append(
            Node(
                type=NodeType.DOCUMENT,
                properties={
                    "page_content": chunk["content"],
                    "document_metadata": chunk.get("metadata") or {},
                },
            )
        )

    try:
        transforms = default_transforms(
            documents=chunks,
            llm=generator_llm,
            embedding_model=generator_embeddings,
        )
        apply_transforms(kg, transforms)
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.generate.transforms_failed", error=str(exc))

    gen = TestsetGenerator(
        llm=generator_llm,
        embedding_model=generator_embeddings,
        knowledge_graph=kg,
    )
    distribution = default_query_distribution(generator_llm)
    testset = gen.generate(testset_size=size, query_distribution=distribution)

    payload = {
        "version": "draft",
        "created_at": None,
        "description": "Synthetic draft — REQUIRES HUMAN REVIEW before use",
        "tenant_id": tenant_id,
        "samples": _testset_to_samples(testset),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return len(payload["samples"])


def _testset_to_samples(testset: Any) -> List[dict]:
    try:
        df = testset.to_pandas()
    except Exception:  # noqa: BLE001
        return []
    samples: List[dict] = []
    for i, row in df.iterrows():
        samples.append(
            {
                "id": f"syn-{i + 1:03d}",
                "category": "conceptual",
                "difficulty": "medium",
                "user_input": row.get("user_input") or row.get("question", ""),
                "reference": row.get("reference") or row.get("ground_truth", ""),
                "reference_contexts": row.get("reference_contexts") or row.get("contexts") or [],
                "tags": ["synthetic", "unreviewed"],
            }
        )
    return samples


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Generate synthetic RAG test data.")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--size", type=int, default=50)
    parser.add_argument("--chunk-limit", type=int, default=500)
    parser.add_argument(
        "--output",
        default="eval/datasets/synthetic_draft.json",
    )
    args = parser.parse_args(argv)

    try:
        count = generate_synthetic(
            tenant_id=args.tenant_id,
            size=args.size,
            chunk_limit=args.chunk_limit,
            output=Path(args.output),
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {count} synthetic samples to {args.output} (human review required).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
