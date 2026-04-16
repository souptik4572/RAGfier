#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"

if [ "${1:-}" != "--yes" ]; then
  echo "Refusing to reset the environment without explicit confirmation." >&2
  echo "Run: ./scripts/reset-environment.sh --yes" >&2
  exit 1
fi

python3 "$ROOT_DIR/scripts/purge-supabase-bucket.py" --yes
"$ROOT_DIR/scripts/truncate-all-tables.sh" --yes

echo "Environment reset completed."
