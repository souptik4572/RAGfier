#!/bin/sh
# Regenerate sql/schema.sql from the current state of the database.
#
# sql/migrations/ is the source of truth for schema *changes*.
# sql/schema.sql is a consolidated *head snapshot* used for reference,
# review, and drift detection.
#
# Run this after adding a new migration:
#   1. Apply the new migration with ./scripts/run-migrations.sh up
#   2. Re-render the snapshot: ./scripts/dump-schema.sh
#   3. Commit both the migration and the updated schema.sql
#
# The script uses `dbmate dump`, which writes a pg_dump-style schema.sql
# plus the list of applied schema_migrations rows. Output is deterministic
# given the same DB state and dbmate version, which makes it suitable for
# CI drift checks (fail if git diff shows schema.sql changes after a dump).
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

if [ -z "${SUPABASE_DB_URL:-}" ]; then
  echo "SUPABASE_DB_URL is required to dump the schema." >&2
  echo "Add it to .env or export it in your shell, then retry." >&2
  exit 1
fi

export DATABASE_URL="${DATABASE_URL:-$SUPABASE_DB_URL}"
export DBMATE_MIGRATIONS_DIR="${DBMATE_MIGRATIONS_DIR:-$ROOT_DIR/sql/migrations}"
export DBMATE_SCHEMA_FILE="${DBMATE_SCHEMA_FILE:-$ROOT_DIR/sql/schema.sql}"

if command -v dbmate >/dev/null 2>&1; then
  exec dbmate dump
fi

if command -v docker >/dev/null 2>&1; then
  exec docker run --rm \
    -v "$ROOT_DIR:/app" \
    -w /app \
    -e DATABASE_URL \
    -e DBMATE_MIGRATIONS_DIR=/app/sql/migrations \
    -e DBMATE_SCHEMA_FILE=/app/sql/schema.sql \
    ghcr.io/amacneil/dbmate dump
fi

echo "dbmate is not installed and docker is unavailable." >&2
echo "Install dbmate or run this script on a machine with Docker." >&2
exit 1
