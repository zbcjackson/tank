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

# --- .claude/ → copy (settings may diverge per worktree) ---
if [[ -d "$ROOT/.claude" ]]; then
  rm -rf "$DEST/.claude"
  cp -r "$ROOT/.claude" "$DEST/.claude"
  echo "Copied .claude/"
fi

# --- web/.env → copy (may diverge per worktree) ---
if [[ -f "$ROOT/web/.env" ]]; then
  cp "$ROOT/web/.env" "$DEST/web/.env"
  echo "Copied web/.env"
fi

# --- Install dependencies for all projects ---
echo ""
echo "Installing dependencies..."

# backend/core (Python/uv)
if [[ -f "$DEST/backend/core/pyproject.toml" ]]; then
  echo "Installing backend/core dependencies..."
  (cd "$DEST/backend/core" && uv sync)
fi

# backend/contracts (Python/uv)
if [[ -f "$DEST/backend/contracts/pyproject.toml" ]]; then
  echo "Installing backend/contracts dependencies..."
  (cd "$DEST/backend/contracts" && uv sync)
fi

# cli (Python/uv)
if [[ -f "$DEST/cli/pyproject.toml" ]]; then
  echo "Installing cli dependencies..."
  (cd "$DEST/cli" && uv sync)
fi

# web (TypeScript/pnpm)
if [[ -f "$DEST/web/package.json" ]]; then
  echo "Installing web dependencies..."
  (cd "$DEST/web" && pnpm install)
fi

# macos (pnpm + Cargo)
if [[ -f "$DEST/macos/package.json" ]]; then
  echo "Installing macos dependencies..."
  (cd "$DEST/macos" && pnpm install)
fi

# test (pnpm)
if [[ -f "$DEST/test/package.json" ]]; then
  echo "Installing test dependencies..."
  (cd "$DEST/test" && pnpm install)
fi

echo ""
echo "Done! cd .worktrees/$NAME to start working."
