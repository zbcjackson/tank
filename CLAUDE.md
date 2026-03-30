# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Tank is a bilingual (Chinese/English) voice assistant monorepo with four sub-projects:

- **`backend/`** — FastAPI server (Python): ASR, TTS, LLM, tools
- **`cli/`** — Terminal UI client (Python/Textual): audio capture, WebSocket client
- **`web/`** — Web frontend (TypeScript/React): browser audio, WebSocket client
- **`macos/`** — Native macOS app (Tauri 2/Rust): wraps web/ as a native .app

## Required Reading

Always read the overall architecture first:
- @ARCHITECTURE.md [ARCHITECTURE.md](ARCHITECTURE.md)

Then read the docs for the sub-project(s) you are working on:

**Backend** (`backend/`):
- @backend/ARCHITECTURE.md [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md)
- @backend/CODING_STANDARDS.md [backend/CODING_STANDARDS.md](backend/CODING_STANDARDS.md)
- @backend/DEVELOPMENT.md [backend/DEVELOPMENT.md](backend/DEVELOPMENT.md)
- @backend/TESTING.md [backend/TESTING.md](backend/TESTING.md)

**CLI** (`cli/`):
- @cli/ARCHITECTURE.md [cli/ARCHITECTURE.md](cli/ARCHITECTURE.md)
- @cli/CODING_STANDARDS.md [cli/CODING_STANDARDS.md](cli/CODING_STANDARDS.md)
- @cli/DEVELOPMENT.md [cli/DEVELOPMENT.md](cli/DEVELOPMENT.md)
- @cli/TESTING.md [cli/TESTING.md](cli/TESTING.md)

**Web** (`web/`):
- @web/ARCHITECTURE.md [web/ARCHITECTURE.md](web/ARCHITECTURE.md)
- @web/CODING_STANDARDS.md [web/CODING_STANDARDS.md](web/CODING_STANDARDS.md)
- @web/DEVELOPMENT.md [web/DEVELOPMENT.md](web/DEVELOPMENT.md)
- @web/TESTING.md [web/TESTING.md](web/TESTING.md)

**macOS** (`macos/`):
- @macos/ARCHITECTURE.md [macos/ARCHITECTURE.md](macos/ARCHITECTURE.md)
- @macos/CODING_STANDARDS.md [macos/CODING_STANDARDS.md](macos/CODING_STANDARDS.md)
- @macos/DEVELOPMENT.md [macos/DEVELOPMENT.md](macos/DEVELOPMENT.md)
- @macos/TESTING.md [macos/TESTING.md](macos/TESTING.md)

> Tip: If you start a session from inside a sub-project directory (e.g. `cd backend && claude`), that directory's CLAUDE.md will be loaded automatically with its own `@` imports — no need to read the others.

## Quick Reference

| Sub-project | Language   | Package Manager | Test Command      |
|-------------|------------|-----------------|-------------------|
| `backend/`  | Python     | uv              | `uv run pytest`   |
| `cli/`      | Python     | uv              | `uv run pytest`   |
| `web/`      | TypeScript | pnpm            | `pnpm test`        |
| `macos/`    | Rust       | pnpm + Cargo    | `cargo test`       |

## Cross-cutting Principles

- Follow TDD: write tests before implementing logic
- Each sub-project has its own virtualenv/node_modules — run commands from within the sub-project directory
- The backend must be running before starting the CLI or web client

## Verification Checklist (MANDATORY)

Run ALL of these every time you finish a task. Do not skip any step.

1. `cd web && pnpm lint` — ESLint
2. `cd web && npx tsc -b --noEmit` — TypeScript type checking (must use `-b` to follow project references; plain `tsc --noEmit` checks nothing on a references-only tsconfig)
3. `cd backend && uv run ruff check src/ tests/` — Python lint
4. `cd backend && uv run pytest` — Backend unit tests (78 tests)
5. `cd cli && uv run ruff check src/ tests/` — CLI Python lint
6. `cd test && pnpm test` — E2E cucumber tests (14 scenarios, requires backend + frontend running)

All six must pass before considering work complete.

## Planning Rules

- Every plan MUST include a "Tests" section — write new E2E or unit tests for any behavior change
- Every plan MUST include the full Verification Checklist as the final step
- Do not create new feature files when existing ones cover the same domain — add scenarios to the existing file
