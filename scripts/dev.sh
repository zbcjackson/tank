#!/usr/bin/env bash
set -euo pipefail

SESSION="tank"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  echo "Usage: $0 [start|stop]"
  echo "  start  Start Docker, backend, and web frontend (default)"
  echo "  stop   Stop tmux session and Docker services"
}

do_start() {
  # Start Docker services (Langfuse)
  echo "Starting Docker services..."
  docker compose -f "$ROOT/docker-compose.yml" up -d

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

  # Stop Docker services
  echo "Stopping Docker services..."
  docker compose -f "$ROOT/docker-compose.yml" down
}

case "${1:-start}" in
  start) do_start ;;
  stop)  do_stop ;;
  *)     usage; exit 1 ;;
esac
