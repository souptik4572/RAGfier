#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

if [ -z "${SUPABASE_DB_URL:-}" ]; then
  echo "SUPABASE_DB_URL is required to run migrations." >&2
  echo "Add it to .env or export it in your shell, then retry." >&2
  exit 1
fi

export DATABASE_URL="${DATABASE_URL:-$SUPABASE_DB_URL}"
export DBMATE_MIGRATIONS_DIR="${DBMATE_MIGRATIONS_DIR:-$ROOT_DIR/sql/migrations}"
export DBMATE_NO_DUMP_SCHEMA="${DBMATE_NO_DUMP_SCHEMA:-true}"
if [ "$#" -eq 0 ]; then
  set -- up
fi

if command -v dbmate >/dev/null 2>&1; then
  exec dbmate "$@"
fi

if command -v docker >/dev/null 2>&1; then
  exec docker run --rm \
    -v "$ROOT_DIR:/app" \
    -w /app \
    -e DATABASE_URL \
    -e DBMATE_MIGRATIONS_DIR \
    -e DBMATE_NO_DUMP_SCHEMA \
    ghcr.io/amacneil/dbmate "$@"
fi

echo "dbmate is not installed and docker is unavailable." >&2
echo "Install dbmate or run this script on a machine with Docker." >&2
exit 1
