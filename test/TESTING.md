# E2E Tests

End-to-end tests live in `/test/` at the repo root. They use **Cucumber + Playwright** to drive the web frontend against a running backend.

## Prerequisites

- Backend running (`uv run tank-backend --reload` in `backend/core/`)
- Web frontend running (`pnpm dev` in `web/`)
- Playwright browsers installed

## Setup

```bash
cd test
pnpm install
pnpm playwright:install
```

## Running

```bash
cd test

# Run all e2e tests (headless)
pnpm test

# Run with browser visible (for debugging)
pnpm test:headed

# Run a specific feature
pnpm test -- features/connection.feature

# Run with a specific tag
pnpm test -- --tags @requires-active-conversation
```

## What They Cover

The e2e tests exercise the full stack: Playwright opens the web app, which connects via WebSocket to the backend. This covers:

- Server startup and module loading
- WebSocket session creation (`ConnectionManager.get_or_create_assistant`)
- Full `Assistant` → `Brain` → `_build_agent_graph` initialization with real config
- Chat message round-trips through the LLM pipeline
- UI state transitions (typing indicator, stop button, mode toggle)

## When to Run

Run e2e tests after any change that touches:
- Config parsing or typed config models
- Server startup (`api/server.py`, `api/manager.py`)
- Assistant/Brain initialization
- WebSocket routing
- Pipeline wiring

Unit tests mock most dependencies, so they miss runtime errors like calling `.get()` on a dataclass or passing the wrong type to a constructor. The e2e tests catch these because they use real objects end-to-end.

## Writing New Tests

Features go in `features/*.feature` (Gherkin syntax). Step definitions go in `steps/*.steps.ts`.

```gherkin
Feature: My feature

  Scenario: Something works
    Given the app is open
    When the user does something
    Then the expected result is visible
```
