#!/usr/bin/env bash
set -euo pipefail

SESSION="tank"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Kill existing session if any
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create session with backend pane
tmux new-session -d -s "$SESSION" -n "dev" -c "$ROOT/backend/core"
tmux send-keys -t "$SESSION" "uv run tank-backend --reload" Enter

# Split horizontally for web frontend
tmux split-window -h -t "$SESSION" -c "$ROOT/web"
tmux send-keys -t "$SESSION" "pnpm dev" Enter

# Attach
tmux attach-session -t "$SESSION"
