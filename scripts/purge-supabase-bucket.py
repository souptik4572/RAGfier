from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv
from supabase import create_client

from app.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Empty the configured Supabase Storage bucket."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required confirmation flag for destructive execution",
    )
    parser.add_argument(
        "--bucket",
        default=None,
        help="override bucket name; defaults to SUPABASE_STORAGE_BUCKET",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.yes:
        print(
            "Refusing to empty the bucket without explicit confirmation.\n"
            "Run: python scripts/purge-supabase-bucket.py --yes",
            file=sys.stderr,
        )
        return 1

    load_dotenv()
    settings = get_settings()
    bucket_name = args.bucket or settings.supabase_storage_bucket
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required.",
            file=sys.stderr,
        )
        return 1
    if not bucket_name:
        print("SUPABASE_STORAGE_BUCKET is required.", file=sys.stderr)
        return 1

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    client.storage.empty_bucket(bucket_name)
    print(f"Emptied Supabase bucket: {bucket_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
