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

if [ -z "${SUPABASE_URL:-}" ] || [ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then
  echo "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required to delete users." >&2
  exit 1
fi

run_psql() {
  if command -v psql >/dev/null 2>&1; then
    psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
    return $?
  fi

  if command -v docker >/dev/null 2>&1; then
    docker run --rm \
      -v "$ROOT_DIR:/workspace" \
      -w /workspace \
      postgres:16-alpine \
      psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$SQL_FILE"
    return $?
  fi

  echo "psql is not installed and docker is unavailable." >&2
  echo "Install psql or run this script on a machine with Docker." >&2
  return 1
}

echo "[1/2] Truncating application tables..."
run_psql

echo "[2/2] Deleting all auth users via Supabase Admin API..."

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to delete users via the Supabase Admin API." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required to delete users via the Supabase Admin API." >&2
  exit 1
fi

SUPABASE_URL_TRIMMED="${SUPABASE_URL%/}"
PER_PAGE=1000
TOTAL_DELETED=0

while :; do
  LIST_RESP=$(curl -sS -G \
    "$SUPABASE_URL_TRIMMED/auth/v1/admin/users" \
    -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
    -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
    --data-urlencode "page=1" \
    --data-urlencode "per_page=$PER_PAGE")

  USER_IDS=$(echo "$LIST_RESP" | jq -r '.users[]?.id // empty')

  if [ -z "$USER_IDS" ]; then
    break
  fi

  for USER_ID in $USER_IDS; do
    HTTP_STATUS=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
      "$SUPABASE_URL_TRIMMED/auth/v1/admin/users/$USER_ID" \
      -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
      -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY")

    if [ "$HTTP_STATUS" != "200" ] && [ "$HTTP_STATUS" != "204" ]; then
      echo "Failed to delete user $USER_ID (HTTP $HTTP_STATUS)." >&2
      exit 1
    fi

    TOTAL_DELETED=$((TOTAL_DELETED + 1))
  done
done

echo "Deleted $TOTAL_DELETED user(s)."
