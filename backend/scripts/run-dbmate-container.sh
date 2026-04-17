#!/bin/sh
set -eu

if [ -z "${SUPABASE_DB_URL:-}" ]; then
  echo "SUPABASE_DB_URL is not set for the migrate container." >&2
  echo "Add SUPABASE_DB_URL to .env before running docker compose up --build." >&2
  exit 1
fi

case "$SUPABASE_DB_URL" in
  *localhost*|*127.0.0.1*|*"[::1]"*|*"@::1:"*)
    echo "SUPABASE_DB_URL points at localhost, which is not reachable from inside Docker." >&2
    echo "Use the remote Supabase Postgres host, or host.docker.internal for a DB running on your machine." >&2
    exit 1
    ;;
esac

export DATABASE_URL="$SUPABASE_DB_URL"
export DBMATE_MIGRATIONS_DIR="${DBMATE_MIGRATIONS_DIR:-/db/sql/migrations}"
export DBMATE_NO_DUMP_SCHEMA="${DBMATE_NO_DUMP_SCHEMA:-true}"

exec dbmate up
