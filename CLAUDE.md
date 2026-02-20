# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Tank is a bilingual (Chinese/English) voice assistant monorepo with three sub-projects:

- **`backend/`** — FastAPI server (Python): ASR, TTS, LLM, tools
- **`cli/`** — Terminal UI client (Python/Textual): audio capture, WebSocket client
- **`web/`** — Web frontend (TypeScript/React): browser audio, WebSocket client

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

> Tip: If you start a session from inside a sub-project directory (e.g. `cd backend && claude`), that directory's CLAUDE.md will be loaded automatically with its own `@` imports — no need to read the others.

## Quick Reference

| Sub-project | Language   | Package Manager | Test Command      |
|-------------|------------|-----------------|-------------------|
| `backend/`  | Python     | uv              | `uv run pytest`   |
| `cli/`      | Python     | uv              | `uv run pytest`   |
| `web/`      | TypeScript | npm             | `npx vitest run`  |

## Cross-cutting Principles

- Follow TDD: write tests before implementing logic
- Each sub-project has its own virtualenv/node_modules — run commands from within the sub-project directory
- The backend must be running before starting the CLI or web client
