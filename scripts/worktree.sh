#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKTREES_DIR="$ROOT/.worktrees"

usage() {
  echo "Usage: $0 <name>"
  echo ""
  echo "Creates a git worktree at .worktrees/<name> on branch feature/<name>."
  echo "Symlinks models/ and copies .env into the worktree."
  exit 1
}

if [[ $# -lt 1 || -z "$1" ]]; then
  usage
fi

NAME="$1"
BRANCH="feature/$NAME"
DEST="$WORKTREES_DIR/$NAME"

if [[ -d "$DEST" ]]; then
  echo "Error: worktree '$DEST' already exists."
  exit 1
fi

# Create worktree with a new branch based on HEAD
echo "Creating worktree at .worktrees/$NAME (branch: $BRANCH)..."
git -C "$ROOT" worktree add -b "$BRANCH" "$DEST"

# --- backend/models → symlink (large binary assets, ~500MB+) ---
if [[ -d "$ROOT/backend/models" ]]; then
  rm -rf "$DEST/backend/models"
  ln -s "$ROOT/backend/models" "$DEST/backend/models"
  echo "Linked backend/models/"
fi

# --- backend/data → symlink (speaker DB + audio samples) ---
if [[ -d "$ROOT/backend/data" ]]; then
  rm -rf "$DEST/backend/data"
  ln -s "$ROOT/backend/data" "$DEST/backend/data"
  echo "Linked backend/data/"
fi

# --- backend/core/.env → copy (may diverge per worktree) ---
if [[ -f "$ROOT/backend/core/.env" ]]; then
  cp "$ROOT/backend/core/.env" "$DEST/backend/core/.env"
  echo "Copied backend/core/.env"
fi

# --- .claude/ → copy (settings, rules, project config) ---
if [[ -d "$ROOT/.claude" ]]; then
  cp -r "$ROOT/.claude" "$DEST/.claude"
  echo "Copied .claude/"
fi

echo ""
echo "Done! cd .worktrees/$NAME to start working."
