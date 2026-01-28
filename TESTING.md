# Testing Guidelines

This document provides comprehensive testing guidelines for the Tank Voice Assistant project. All tests should follow these principles and practices.

## Test-Driven Development (TDD)

**Follow Test-Driven Development (TDD):**
- Write tests BEFORE implementing any logic changes
- Run tests frequently throughout development
- Ensure all tests pass before committing changes
- Maintain high test coverage for critical components

## Testing Workflow

1. Write a failing test that describes the desired behavior
2. Implement the minimal code needed to make the test pass
3. Refactor the code while keeping tests green
4. Run the full test suite to ensure no regressions

## Testing Commands

```bash
# Run all tests
uv run python -m pytest tests/

# Run with coverage
uv run python -m pytest tests/ --cov=src/voice_assistant

# Run specific test file
uv run python -m pytest tests/test_tools.py

# Run tests in watch mode during development
uv run python -m pytest tests/ --watch
```

## Testing Framework

- **Framework**: `pytest` with `pytest-asyncio`
- **Location**: `tests/`
- **Test Structure**: Tests should be organized by component/module

## Key Testing Practices

### Focus on Business Logic

- **Prefer testing business logic/behavior over pure data structures**
  - Avoid standalone tests for simple containers (e.g., plain `@dataclass`) unless they contain non-trivial validation or behavior
  - Test the behavior and interactions, not just data structure properties

### Avoid False Positives

- **Tests should verify actual behavior, not just pass trivially**
  - Ensure tests would fail if the behavior is broken
  - Avoid tests that pass even when functionality is incorrect
  - Verify actual outcomes, not just that code runs without errors

### Avoid Redundant Conditionals

- **Use assertions instead of conditional checks in tests**
  - Avoid patterns like `if callback:` that skip test logic
  - Use assertions to fail fast with clear error messages
  - Example: `assert callback is not None, "Expected callback to be set"` instead of `if callback: ...`

### Test Configuration and Functionality Together

- **When testing configuration parameters, also verify functionality works**
  - Don't test only parameter passing without verifying behavior
  - Verify that the configured parameters actually produce the expected behavior
  - Example: If testing audio format configuration, verify that audio is actually captured with that format

### Mock External Dependencies

- Mock external APIs (LLM, Search) and hardware (Audio I/O) in tests
- Use `unittest.mock` or `pytest` fixtures for mocking
- Ensure mocks are properly configured to simulate real behavior

### Test Edge Cases and Error Conditions

- Test all tool functionality and edge cases
- Test error conditions and exception handling
- Verify configuration validation and defaults
- Test boundary conditions and error paths

### Async Testing

- Use async tests for async components
- Ensure async tests are properly marked or configured
- Use `pytest-asyncio` for async test support

## Test Quality Checklist

Before committing tests, ensure:

- [ ] Tests verify actual behavior, not just that code runs
- [ ] Tests would fail if the behavior is broken
- [ ] No redundant conditional checks that skip test logic
- [ ] Configuration tests also verify functionality
- [ ] External dependencies are properly mocked
- [ ] Edge cases and error conditions are covered
- [ ] Tests are focused on business logic, not simple data structures
- [ ] Async tests are properly configured

## Running Tests Before Commits

- Run full suite before major commits
- Ensure all tests pass locally before pushing
- Check test coverage for new code
