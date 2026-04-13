#!/usr/bin/env bash
set -euo pipefail

# Creates (or reuses) a tenant, ensures a user has
# app_metadata.organization_id set to that tenant, then prints a fresh JWT.
#
# Required env vars:
#   SUPABASE_URL
#   SERVICE_ROLE_KEY
#   ANON_KEY
#   TENANT_NAME
#   TENANT_SLUG
#   USER_EMAIL
#   USER_PASSWORD
#
# Optional env vars:
#   QUIET=true   # prints only the JWT token

usage() {
  cat <<'EOF'
Usage:
  SUPABASE_URL="https://<project-ref>.supabase.co" \
  SERVICE_ROLE_KEY="<service-role-key>" \
  ANON_KEY="<anon-key>" \
  TENANT_NAME="Acme Inc" \
  TENANT_SLUG="acme-inc" \
  USER_EMAIL="owner@acme-inc.com" \
  USER_PASSWORD="StrongPassword123!" \
  ./scripts/generate_jwt.sh

Optional:
  QUIET=true ./scripts/generate_jwt.sh
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
}

require_env() {
  local var_name="$1"
  if [[ -z "${!var_name:-}" ]]; then
    echo "Error: missing required env var: $var_name" >&2
    usage
    exit 1
  fi
}

log() {
  if [[ "${QUIET:-false}" != "true" ]]; then
    echo "$1"
  fi
}

has_missing_required_env() {
  local required_vars=(
    SUPABASE_URL
    SERVICE_ROLE_KEY
    ANON_KEY
    TENANT_NAME
    TENANT_SLUG
    USER_EMAIL
    USER_PASSWORD
  )
  local var_name
  for var_name in "${required_vars[@]}"; do
    if [[ -z "${!var_name:-}" ]]; then
      return 0
    fi
  done
  return 1
}

load_env_file_if_exists() {
  local env_file="$1"
  if [[ -f "$env_file" ]]; then
    # Export all loaded variables so they are visible to subprocesses.
    set -a
    # shellcheck source=/dev/null
    . "$env_file"
    set +a
  fi
}

require_cmd curl
require_cmd jq

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if has_missing_required_env; then
  load_env_file_if_exists "$SCRIPT_DIR/.env"
fi
if has_missing_required_env; then
  load_env_file_if_exists "$SCRIPT_DIR/../.env"
fi

require_env SUPABASE_URL
require_env SERVICE_ROLE_KEY
require_env ANON_KEY
require_env TENANT_NAME
require_env TENANT_SLUG
require_env USER_EMAIL
require_env USER_PASSWORD

SUPABASE_URL="${SUPABASE_URL%/}"

log "[1/4] Creating or reusing tenant..."
TENANT_PAYLOAD=$(jq -n \
  --arg name "$TENANT_NAME" \
  --arg slug "$TENANT_SLUG" \
  '{name:$name, slug:$slug, plan:"free", settings:{}}')

TENANT_RESP=$(curl -sS -X POST \
  "$SUPABASE_URL/rest/v1/tenants?on_conflict=slug" \
  -H "apikey: $SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -H "Prefer: resolution=merge-duplicates,return=representation" \
  -d "$TENANT_PAYLOAD")

TENANT_ID=$(echo "$TENANT_RESP" | jq -r '.[0].id // empty')
if [[ -z "$TENANT_ID" ]]; then
  echo "Error: failed to create/find tenant. Response:" >&2
  echo "$TENANT_RESP" | jq . >&2 || echo "$TENANT_RESP" >&2
  exit 1
fi

log "[2/4] Creating user (or reusing existing user)..."
USER_CREATE_PAYLOAD=$(jq -n \
  --arg email "$USER_EMAIL" \
  --arg password "$USER_PASSWORD" \
  --arg org "$TENANT_ID" \
  '{
    email:$email,
    password:$password,
    email_confirm:true,
    app_metadata:{organization_id:$org}
  }')

USER_CREATE_RESP=$(curl -sS -X POST \
  "$SUPABASE_URL/auth/v1/admin/users" \
  -H "apikey: $SERVICE_ROLE_KEY" \
  -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
  -H "Content-Type: application/json" \
  -d "$USER_CREATE_PAYLOAD")

USER_ID=$(echo "$USER_CREATE_RESP" | jq -r '.id // empty')

if [[ -z "$USER_ID" ]]; then
  # User likely exists; fetch and update app_metadata.
  EXISTING_USER_RESP=$(curl -sS -G \
    "$SUPABASE_URL/auth/v1/admin/users" \
    -H "apikey: $SERVICE_ROLE_KEY" \
    -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
    --data-urlencode "page=1" \
    --data-urlencode "per_page=1000")

  USER_ID=$(echo "$EXISTING_USER_RESP" | jq -r --arg email "$USER_EMAIL" '.users[] | select(.email == $email) | .id' | head -n 1)
  if [[ -z "$USER_ID" ]]; then
    echo "Error: failed to create/find user. Create response:" >&2
    echo "$USER_CREATE_RESP" | jq . >&2 || echo "$USER_CREATE_RESP" >&2
    exit 1
  fi

  USER_UPDATE_PAYLOAD=$(jq -n \
    --arg org "$TENANT_ID" \
    '{app_metadata:{organization_id:$org}}')

  curl -sS -X PUT \
    "$SUPABASE_URL/auth/v1/admin/users/$USER_ID" \
    -H "apikey: $SERVICE_ROLE_KEY" \
    -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
    -H "Content-Type: application/json" \
    -d "$USER_UPDATE_PAYLOAD" >/dev/null
fi

log "[3/4] Requesting JWT token via password sign-in..."
LOGIN_PAYLOAD=$(jq -n \
  --arg email "$USER_EMAIL" \
  --arg password "$USER_PASSWORD" \
  '{email:$email, password:$password}')

LOGIN_RESP=$(curl -sS -X POST \
  "$SUPABASE_URL/auth/v1/token?grant_type=password" \
  -H "apikey: $ANON_KEY" \
  -H "Content-Type: application/json" \
  -d "$LOGIN_PAYLOAD")

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // empty')
if [[ -z "$ACCESS_TOKEN" ]]; then
  echo "Error: failed to obtain JWT. Response:" >&2
  echo "$LOGIN_RESP" | jq . >&2 || echo "$LOGIN_RESP" >&2
  exit 1
fi

log "[4/4] Done."
if [[ "${QUIET:-false}" == "true" ]]; then
  echo "$ACCESS_TOKEN"
else
  echo "Tenant ID: $TENANT_ID"
  echo "User ID:   $USER_ID"
  echo "JWT:"
  echo "$ACCESS_TOKEN"
fi
