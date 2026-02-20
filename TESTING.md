# Testing Guidelines

This document provides cross-cutting testing guidelines for the Tank monorepo.

For sub-project details, see:
- [backend/TESTING.md](backend/TESTING.md) — Python/pytest
- [cli/TESTING.md](cli/TESTING.md) — Python/pytest + Textual pilot
- [web/TESTING.md](web/TESTING.md) — Vitest + React Testing Library

## TDD Workflow

1. Write a failing test describing the desired behavior
2. Implement the minimal code to make it pass
3. Refactor while keeping tests green
4. Run the full suite before committing

## Universal Principles

### Test Behavior, Not Implementation

- Test through public interfaces and input/output contracts
- Don't access private methods (`_name`) or internal attributes
- Tests should remain stable when internal implementation changes

### Mock External Dependencies

Always mock:
- Network calls (LLM API, web search, WebSocket)
- Hardware (microphone, speaker, audio devices)
- ML model loading (Whisper, VAD)
- System time (use fixed timestamps)

### No Trivially-Passing Tests

- Every test must fail if the behavior it covers is broken
- Avoid `if callback:` guards that silently skip assertions
- Verify actual output values, not just that code runs without error

### Performance Targets

| Level | Target |
|-------|--------|
| Unit test | < 1 second |
| Integration test | < 2 seconds |
| Full suite | < 30 seconds |

## Test Data

- Generate audio programmatically (numpy sine waves) — no real audio files
- Use fixed timestamps, not `time.time()`
- Use deterministic seeds for any random data

## Test Organization

```
<sub-project>/tests/
├── conftest.py              # Shared fixtures
├── test_<component>.py      # Unit tests
└── test_<component>_integration.py  # Integration tests
```

## Quality Checklist

Before committing:

- [ ] Tests verify actual behavior, not just that code runs
- [ ] Tests would fail if the behavior is broken
- [ ] External dependencies (network, hardware, models) are mocked
- [ ] No access to private methods or internal state
- [ ] Async tests are properly configured
- [ ] Each test completes in < 2 seconds
- [ ] Test data is deterministic (no `time.time()`, no random without seed)
