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

## Testing Performance Principles

**Primary Goals: Fast Execution + Stable Results**

All unit tests should prioritize:
- **Fast execution**: Individual tests should complete in < 2 seconds
- **Stability**: Tests should be deterministic and repeatable
- **No external dependencies**: Avoid real hardware, file I/O, network calls, or model loading

### Performance Targets

- **Unit tests**: < 1 second per test
- **Integration tests**: < 2 seconds per test
- **Full test suite**: < 30 seconds total

## Mock Strategy

### Core Principle

**Minimize mocking while maintaining test speed and stability.**

- **Reduce mocking** for fast, stable components to get more realistic test results
- **Keep mocking** for slow, unstable, or external dependencies
- **Balance**: Prefer real implementations when they're fast enough (< 100ms) and deterministic

### Decision Framework: When to Mock

Use this decision tree to determine whether to mock:

1. **Is it fast?** (< 100ms per test)
   - ✅ **Fast**: Consider using real implementation
   - ❌ **Slow**: Mock it

2. **Is it stable?** (deterministic, no external dependencies)
   - ✅ **Stable**: Consider using real implementation
   - ❌ **Unstable**: Mock it

3. **Is it external?** (network, hardware, file system)
   - ✅ **Internal**: Consider using real implementation
   - ❌ **External**: Mock it

### Mocking Guidelines: DO Mock (Slow, Unstable, or External)

- **ML Model Loading** (slow: 1-10+ seconds)
- **Hardware Interfaces** (unstable: may fail in CI, requires hardware)
- **Network Calls** (slow, unstable: network latency, failures)
- **System Time** (non-deterministic: changes each run) - use fixed timestamps instead
- **File I/O** (slow, path dependencies)

### Mocking ML Models

When testing components that use ML models:

```python
# ✅ Good: Mock model loading and inference
with patch('module.path.load_model') as mock_load:
    mock_model = MagicMock()
    mock_model.inference.return_value = controlled_result
    mock_load.return_value = mock_model

# ❌ Bad: Load real models in unit tests
model = load_real_model()  # Slow, may fail, requires dependencies
```

### Mocking Hardware

When testing audio/video components:

```python
# ✅ Good: Mock hardware interfaces
with patch('sounddevice.InputStream') as mock_stream:
    # Configure mock to simulate hardware behavior
    pass

# ❌ Bad: Use real hardware in tests
stream = sd.InputStream(...)  # May fail in CI, slow, requires hardware
```

## Test Data Generation

### Audio/Media Data

- **Use programmatic generation** instead of real files:
  - Generate numpy arrays in memory
  - Use deterministic algorithms (sine waves, patterns)
  - Avoid random data (or use fixed seeds)

```python
# ✅ Good: Deterministic, fast, no file I/O
def generate_speech_frame(sample_rate=16000, frame_ms=20, frequency=500):
    n_samples = int(sample_rate * frame_ms / 1000)
    t = np.linspace(0, frame_ms/1000, n_samples)
    signal = 0.3 * np.sin(2 * np.pi * frequency * t)
    return signal.astype(np.float32)

# ❌ Bad: File I/O, path dependencies, slow
audio = load_audio_file("test_data/speech.wav")
```

### Timestamps

- **Use fixed, controllable timestamps** instead of system time:
  - Avoid `time.time()` in tests
  - Use fixed base time + calculated offsets
  - Ensures repeatability and avoids timing-related flakiness

```python
# ✅ Good: Fixed, predictable timestamps
base_time = 1000.0  # Fixed starting point
frames = [
    AudioFrame(..., timestamp_s=base_time + i * 0.02)
    for i in range(count)
]

# ❌ Bad: System time, non-deterministic
frames = [
    AudioFrame(..., timestamp_s=time.time())  # Changes each run
    for i in range(count)
]
```

## Black-Box Testing Strategy

### Principle: Test Behavior, Not Implementation

When testing complex components with internal state:

- **Test through input/output contracts**, not internal variables
- **Verify observable behavior**, not internal implementation details
- **Tests should remain stable** when internal implementation changes

### Example: Testing State Machines

```python
# ✅ Good: Black-box test - verify output sequence
def test_state_machine_transitions():
    component = Component()
    inputs = [input1, input2, input3]
    outputs = [component.process(i) for i in inputs]
    
    # Verify output sequence matches expected behavior
    assert outputs[0].status == Status.INITIAL
    assert outputs[1].status == Status.PROCESSING
    assert outputs[2].status == Status.COMPLETE

# ❌ Bad: White-box test - checks internal state
def test_state_machine_transitions():
    component = Component()
    # Don't check internal _state variable directly
    assert component._internal_state == "processing"  # Fragile!
```

### Example: Testing Buffering/Chunking

```python
# ✅ Good: Verify behavior through output timing/content
def test_chunk_buffering():
    component = Component()
    # Send small inputs
    result1 = component.process(small_input1)
    result2 = component.process(small_input2)
    
    # Verify output contains accumulated data
    assert len(result2.output_data) >= expected_chunk_size
    # Don't check internal buffer size

# ❌ Bad: Check internal buffer state
def test_chunk_buffering():
    component = Component()
    # Don't access internal implementation
    assert len(component._internal_buffer) == 512  # Fragile!
```

## Integration Testing Strategy

### When to Write Integration Tests

Integration tests verify:
- **Component interactions** (how components work together)
- **End-to-end data flow** (input → processing → output)
- **Configuration effects** (parameters actually work as expected)

### Integration Test Scope

- **Mock external dependencies** (models, hardware, APIs)
- **Keep component interactions real** (test actual method calls between components)
- **Verify output contracts** (check final outputs, not intermediate states)

```python
# ✅ Good: Integration test with mocked external deps
def test_segmenter_produces_utterance():
    # Mock external model
    with mock_vad_model():
        segmenter = UtteranceSegmenter(...)
        # Send frames through real component
        for frame in test_frames:
            segmenter.handle(frame)
        
        # Verify output queue contains expected result
        assert not utterance_queue.empty()
        utterance = utterance_queue.get()
        assert isinstance(utterance, Utterance)
```

### Thread Testing Strategy

- **Unit tests: Use synchronous calls** (avoid thread startup/waiting)
  - Directly call `handle()` or `process()` methods
  - Faster and more stable

```python
# ✅ Good: Synchronous call, fast and stable
component = Component()
component.handle(item)  # Direct call, no thread overhead

# ⚠️ Use real threads only when necessary (integration tests)
component.start()  # Only in integration tests
time.sleep(0.1)    # Only when testing thread lifecycle
```

## Test Organization

### Test Hierarchy

1. **Unit Tests** (`test_<component>.py`)
   - Test individual components in isolation
   - **Mock only slow/unstable dependencies** (model loading, hardware, network)
   - **Use real implementations** for fast/stable components (numpy, data structures, pure logic)
   - Fast execution (< 1 second each)
   - Focus on business logic and edge cases

2. **Integration Tests** (`test_<component>_integration.py` or within same file)
   - Test component interactions
   - **Mock only external dependencies** (hardware, network, large model loading)
   - **Use real implementations** for component interactions and fast operations
   - Verify end-to-end data flow
   - Slightly slower (< 2 seconds each)
   - May use real small models if fast enough (< 1s load, < 100ms inference)

3. **End-to-End Tests** (optional, separate suite)
   - Test complete workflows
   - Use real dependencies (with proper setup/teardown)
   - Run less frequently (CI/CD pipeline, manual testing)
   - Marked with `@pytest.mark.slow` or `@pytest.mark.e2e`

### Test File Structure

```
tests/
├── test_vad.py              # Unit tests for VAD component
├── test_segmenter.py        # Unit tests for Segmenter
├── test_segmenter_integration.py  # Integration tests
├── fixtures/
│   └── audio_helpers.py     # Reusable test data generators
└── conftest.py              # Shared pytest fixtures
```

## Test Data Fixtures

### Reusable Test Data Generators

Create fixtures for common test data patterns:

```python
# tests/fixtures/audio_helpers.py
@pytest.fixture
def generate_silence_frame(sample_rate=16000, frame_ms=20):
    """Generate a silence audio frame."""
    n_samples = int(sample_rate * frame_ms / 1000)
    return np.zeros(n_samples, dtype=np.float32)

@pytest.fixture
def generate_speech_frame(sample_rate=16000, frame_ms=20, frequency=500):
    """Generate a speech-like audio frame."""
    n_samples = int(sample_rate * frame_ms / 1000)
    t = np.linspace(0, frame_ms/1000, n_samples)
    signal = 0.3 * np.sin(2 * np.pi * frequency * t)
    return signal.astype(np.float32)
```

## Test Quality Checklist (Updated)

Before committing tests, ensure:

- [ ] Tests verify actual behavior, not just that code runs
- [ ] Tests would fail if the behavior is broken
- [ ] No redundant conditional checks that skip test logic
- [ ] Configuration tests also verify functionality
- [ ] External dependencies are properly mocked
- [ ] Edge cases and error conditions are covered
- [ ] Tests are focused on business logic, not simple data structures
- [ ] Async tests are properly configured
- [ ] **Tests complete in < 2 seconds each**
- [ ] **Tests use deterministic, repeatable data**
- [ ] **Tests don't depend on external files or hardware** (unless explicitly marked as integration/E2E)
- [ ] **Black-box tests verify behavior through input/output**
- [ ] **Mocking is minimized** - only mock slow/unstable/external dependencies
- [ ] **Real implementations used** for fast/stable components to get realistic results

## Running Tests Before Commits

- Run full suite before major commits
- Ensure all tests pass locally before pushing
- Check test coverage for new code
- Verify test execution time is acceptable (< 30 seconds for full suite)
