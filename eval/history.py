"""CLI: list recent evaluation runs for a tenant.

Usage:
    python -m eval.history --tenant-id <uuid> --last 10
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from app.models.database import get_service_client
from app.utils.logger import configure_logging
from eval.store import list_runs


def _fmt(score: Any) -> str:
    if score is None:
        return "   n/a"
    try:
        return f"{float(score):6.3f}"
    except (TypeError, ValueError):
        return "   n/a"


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Show recent evaluation runs.")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--last", type=int, default=10)
    args = parser.parse_args(argv)

    client = get_service_client()
    runs = list_runs(client, args.tenant_id, limit=args.last)
    if not runs:
        print("No evaluation runs found for this tenant.")
        return 0

    header = (
        f"{'id':36}  {'dataset':14}  {'trigger':9}  {'status':10}  "
        f"{'pass':5}  {'faith':6}  {'ans_rel':7}  {'ctx_p':6}  {'ctx_r':6}  created_at"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        print(
            f"{str(run.get('id', ''))[:36]:36}  "
            f"{str(run.get('dataset_version', ''))[:14]:14}  "
            f"{str(run.get('trigger', ''))[:9]:9}  "
            f"{str(run.get('status', ''))[:10]:10}  "
            f"{str(run.get('passed', ''))[:5]:5}  "
            f"{_fmt(run.get('faithfulness_avg'))}  "
            f"{_fmt(run.get('answer_relevancy_avg'))}  "
            f"{_fmt(run.get('context_precision_avg'))}  "
            f"{_fmt(run.get('context_recall_avg'))}  "
            f"{run.get('created_at', '')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
