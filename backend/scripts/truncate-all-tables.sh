#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
SQL_FILE="$ROOT_DIR/sql/admin/202604160101_truncate_all_tables.sql"

if [ "${1:-}" != "--yes" ]; then
  echo "Refusing to truncate all tables without explicit confirmation." >&2
  echo "Run: ./scripts/truncate-all-tables.sh --yes" >&2
  exit 1
fi

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

if [ -z "${SUPABASE_DB_URL:-}" ]; then
  echo "SUPABASE_DB_URL is required to truncate tables." >&2
  exit 1
fi

if command -v psql >/dev/null 2>&1; then
  exec psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
fi

if command -v docker >/dev/null 2>&1; then
  exec docker run --rm \
    -v "$ROOT_DIR:/workspace" \
    -w /workspace \
    postgres:16-alpine \
    psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
fi

echo "psql is not installed and docker is unavailable." >&2
echo "Install psql or run this script on a machine with Docker." >&2
exit 1
