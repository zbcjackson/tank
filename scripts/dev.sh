#!/usr/bin/env bash
set -euo pipefail

SESSION="tank"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  echo "Usage: $0 [start|stop] [--langfuse]"
  echo "  start         Start backend and web frontend (default)"
  echo "  stop          Stop tmux session (backend + web)"
  echo ""
  echo "  --langfuse    Also start/stop the Docker services (Langfuse stack)."
  echo "                Skipped by default — the backend runs fine without"
  echo "                Langfuse (tracing is disabled unless LANGFUSE_* is set)."
}

# Parse the --langfuse flag from any position.
LANGFUSE=0
for arg in "$@"; do
  case "$arg" in
    --langfuse) LANGFUSE=1 ;;
  esac
done

do_start() {
  # Start Docker services (Langfuse) — opt-in via --langfuse
  if [ "$LANGFUSE" -eq 1 ]; then
    echo "Starting Docker services (Langfuse)..."
    docker compose -f "$ROOT/docker-compose.yml" up -d
  else
    echo "Skipping Langfuse Docker services (pass --langfuse to enable)."
  fi

  # Kill existing tmux session if any
  tmux kill-session -t "$SESSION" 2>/dev/null || true

  # Create session with backend pane
  tmux new-session -d -s "$SESSION" -n "dev" -c "$ROOT/backend/core"
  tmux send-keys -t "$SESSION" "uv run tank-backend --reload" Enter

  # Split horizontally for web frontend
  tmux split-window -h -t "$SESSION" -c "$ROOT/web"
  tmux send-keys -t "$SESSION" "pnpm dev" Enter

  # Attach
  tmux attach-session -t "$SESSION"
}

do_stop() {
  # Stop tmux session
  echo "Stopping tmux session..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true

  # Stop Docker services — mirrors the --langfuse start flag
  if [ "$LANGFUSE" -eq 1 ]; then
    echo "Stopping Docker services (Langfuse)..."
    docker compose -f "$ROOT/docker-compose.yml" down
  fi
}

case "${1:-start}" in
  start) do_start ;;
  stop)  do_stop ;;
  -h|--help) usage ;;
  *)     usage; exit 1 ;;
esac
