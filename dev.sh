#!/usr/bin/env bash
# dev.sh — start RAGfier locally: migrations → backend → frontend
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
FRONTEND_DIR="$REPO_ROOT/frontend"

# ── colour helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[dev]${NC} $*"; }
success() { echo -e "${GREEN}[dev]${NC} $*"; }
warn()    { echo -e "${YELLOW}[dev]${NC} $*"; }
die()     { echo -e "${RED}[dev] ERROR:${NC} $*" >&2; exit 1; }

# ── cleanup on exit ────────────────────────────────────────────────────────
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  info "Shutting down…"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null && info "Frontend stopped (pid $FRONTEND_PID)"
  [ -n "$BACKEND_PID"  ] && kill "$BACKEND_PID"  2>/dev/null && info "Backend stopped  (pid $BACKEND_PID)"
  wait 2>/dev/null
  success "Done."
}
trap cleanup INT TERM EXIT

# ── 1. backend/.env ────────────────────────────────────────────────────────
if [ ! -f "$BACKEND_DIR/.env" ]; then
  die "backend/.env not found. Copy backend/.env.example to backend/.env and fill in values."
fi

# ── 2. Python venv ─────────────────────────────────────────────────────────
VENV_DIR="$BACKEND_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
  info "Creating Python venv…"
  if command -v uv >/dev/null 2>&1; then
    (cd "$BACKEND_DIR" && uv venv)
  else
    python3 -m venv "$VENV_DIR"
  fi
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

if [ ! -x "$VENV_DIR/bin/uvicorn" ]; then
  info "Installing backend dependencies…"
  if command -v uv >/dev/null 2>&1; then
    (cd "$BACKEND_DIR" && uv pip install -r requirements.txt --quiet)
  else
    "$PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet
  fi
else
  info "Reusing existing venv at backend/.venv"
fi

# ── 3. DB migrations ────────────────────────────────────────────────────────
info "Running DB migrations…"
(cd "$BACKEND_DIR" && bash scripts/run-migrations.sh up)
success "Migrations applied."

# ── 4. Frontend dependencies ───────────────────────────────────────────────
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  info "Installing frontend dependencies (npm ci)…"
  (cd "$FRONTEND_DIR" && npm ci --silent)
fi

# frontend/.env.local — create from example if missing
if [ ! -f "$FRONTEND_DIR/.env.local" ]; then
  warn "frontend/.env.local not found — creating from .env.local.example."
  cp "$FRONTEND_DIR/.env.local.example" "$FRONTEND_DIR/.env.local"
fi

# ── 5. Start backend ────────────────────────────────────────────────────────
# Free port 8000 if a stale process is still bound to it
if lsof -ti :8000 >/dev/null 2>&1; then
  warn "Port 8000 is in use — killing stale process(es)…"
  kill $(lsof -ti :8000) 2>/dev/null || true
  sleep 1
fi
info "Starting backend on http://localhost:8000 …"
(
  cd "$BACKEND_DIR"
  # shellcheck disable=SC1091
  set -a; . .env; set +a
  "$VENV_DIR/bin/uvicorn" app.main:app --reload --port 8000
) &
BACKEND_PID=$!

# Give uvicorn a moment to bind before starting the frontend
info "Waiting for backend to become ready…"
for i in $(seq 1 20); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    success "Backend is up."
    break
  fi
  if [ "$i" -eq 20 ]; then
    die "Backend did not become healthy after 20 seconds."
  fi
  sleep 1
done

# ── 6. Start frontend ──────────────────────────────────────────────────────
# Free port 3000 if a stale process is still bound to it
if lsof -ti :3000 >/dev/null 2>&1; then
  warn "Port 3000 is in use — killing stale process(es)…"
  kill $(lsof -ti :3000) 2>/dev/null || true
  sleep 1
fi
info "Starting frontend on http://localhost:3000 …"
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

success "RAGfier is running."
echo ""
echo -e "  Backend  → ${CYAN}http://localhost:8000${NC}"
echo -e "  Frontend → ${CYAN}http://localhost:3000${NC}"
echo ""
echo "Press Ctrl-C to stop both services."

# ── 7. Block until Ctrl-C / SIGTERM ───────────────────────────────────────
while true; do
  sleep 1
done
