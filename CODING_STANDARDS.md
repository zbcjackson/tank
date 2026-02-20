# Coding Standards

This document defines cross-cutting coding standards for the Tank monorepo.

For language-specific standards, see:
- [backend/CODING_STANDARDS.md](backend/CODING_STANDARDS.md) — Python/FastAPI
- [cli/CODING_STANDARDS.md](cli/CODING_STANDARDS.md) — Python/Textual
- [web/CODING_STANDARDS.md](web/CODING_STANDARDS.md) — TypeScript/React

## Universal Principles

### Avoid Unnecessary Abstraction

- Don't wrap functionality that already provides what you need
- Don't duplicate logic that a dependency already handles
- Three similar lines of code is better than a premature abstraction

### Test-Driven Development

- Write tests before implementing logic
- Tests verify observable behavior, not implementation details
- Tests must fail when the behavior is broken — no trivially-passing tests

### Error Handling

- Graceful degradation: a failing component should not crash the whole system
- Log errors with context; show user-friendly messages in the UI
- Never swallow errors silently

### Logging

- Use the language's standard logging facility (`logging` in Python, `console.*` in TypeScript)
- Use appropriate levels: DEBUG for internals, INFO for lifecycle events, ERROR for failures
- Never use `print` / `console.log` for production logging

### One Responsibility Per File

- One class per file (Python), one primary export per file (TypeScript)
- Keep `__init__.py` / `index.ts` as re-export-only files
- Name files after the class/component they contain

## Python-specific (backend + cli)

- Relative imports within a package (`from ..core.events import X`)
- Type hints on all function signatures
- All I/O must be `async`; use thread pools for CPU-bound work
- PEP 8, 100-char line limit

## TypeScript-specific (web)

- Strict mode; avoid `any`
- Functional React components only; logic in custom hooks
- Tailwind utility classes for styling; `clsx` for conditionals
- Functional updater form for state that depends on previous state
