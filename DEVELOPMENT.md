# Development Guide

This document provides top-level development commands for the Tank monorepo.

For sub-project details, see:
- [backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)
- [cli/DEVELOPMENT.md](cli/DEVELOPMENT.md)
- [web/DEVELOPMENT.md](web/DEVELOPMENT.md)

## Quick Start

### Prerequisites

```bash
cd backend
uv sync
cp .env.example .env   # Edit with your API keys

cd ../web
pnpm install
```

### Start Backend + Web (recommended)

```bash
scripts/dev.sh
```

This launches a tmux session named `tank` with two panes:
- **Left pane**: backend (`uv run tank-backend --reload`)
- **Right pane**: web frontend (`pnpm dev`)

To check logs for debugging, attach to the session and switch panes:

```bash
tmux attach -t tank       # Attach to the session
# Ctrl-b ←/→              # Switch between backend / web panes
# Ctrl-b d                # Detach without stopping
```

### Start the CLI (optional)

```bash
cd cli && uv sync && uv run tank
```

## Running Tests

Each sub-project has its own test suite. Run from within the sub-project directory:

```bash
# Backend
cd backend && uv run pytest

# CLI
cd cli && uv run pytest

# Web (once Vitest is configured)
cd web && npx vitest run
```

## Package Managers

| Sub-project | Manager | Install | Test |
|-------------|---------|---------|------|
| `backend/`  | uv      | `uv sync` | `uv run pytest` |
| `cli/`      | uv      | `uv sync` | `uv run pytest` |
| `web/`      | pnpm    | `pnpm install` | `pnpm vitest run` |

## Environment Setup

- `backend/.env` — required; copy from `.env.example` and add `LLM_API_KEY`
- `SERPER_API_KEY` — optional, enables web search tool
- Python 3.10+ required for backend and CLI
- Node.js 18+ required for web

## Hardware Dependencies

`sounddevice` and Whisper require audio hardware or mocked interfaces in CI/headless environments. The web client uses the browser's `getUserMedia` API.
