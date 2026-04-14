"""Post-process CI artifacts into eval_runs rows.

Invoked by the GitHub Actions workflow after `deepeval test run`. Reads
the most recent JSON report from eval/reports/ and upserts it into the
Supabase `eval_runs` table so the history viewer and dashboards can
display the result.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from app.models.database import get_service_client
from app.utils.logger import configure_logging, get_logger

logger = get_logger(__name__)


def _latest_report(reports_dir: Path) -> Optional[Path]:
    if not reports_dir.exists():
        return None
    candidates = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def _update_run(
    client: Any, run_id: str, *, git_sha: str, git_branch: str, trigger: str
) -> None:
    client.table("eval_runs").update(
        {
            "git_sha": git_sha,
            "git_branch": git_branch,
            "trigger": trigger,
        }
    ).eq("id", run_id).execute()


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description="Store CI eval results in Supabase.")
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--git-branch", required=True)
    parser.add_argument("--trigger", default="ci")
    parser.add_argument("--reports-dir", default="eval/reports")
    args = parser.parse_args(argv)

    reports_dir = Path(args.reports_dir)
    report_path = _latest_report(reports_dir)
    if not report_path:
        print("warning: no evaluation report found; nothing to upload.")
        return 0

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: could not parse {report_path}: {exc}", file=sys.stderr)
        return 2

    run_id = payload.get("run_id")
    if not run_id:
        print("error: report missing run_id", file=sys.stderr)
        return 2

    client = get_service_client()
    try:
        _update_run(
            client,
            run_id,
            git_sha=args.git_sha,
            git_branch=args.git_branch,
            trigger=args.trigger,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.store_ci.update_failed", error=str(exc), run_id=run_id)
        return 1

    print(f"Updated eval_runs row {run_id} with git sha {args.git_sha}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
