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

See [DEVELOPMENT.md](DEVELOPMENT.md) for testing commands.

## Testing Framework

- **Framework**: `pytest` with `pytest-asyncio`
- **Location**: `tests/`
- **Test Structure**: Tests should be organized by component/module

## Key Testing Practices

### Focus on Business Logic

- **Prefer testing business logic/behavior over pure data structures**
  - Avoid standalone tests for simple containers (e.g., plain `@dataclass`) unless they contain non-trivial validation or behavior
  - Test the behavior and interactions, not just data structure properties

### Test Behavior, Not Implementation Details

- **Tests should verify observable behavior, not internal implementation**
  - See [CODING_STANDARDS.md](CODING_STANDARDS.md) for detailed testing principles
  - Test through public interfaces and input/output contracts
  - Avoid testing private methods (`_method_name`) or internal attributes (`_attribute_name`)
  - Avoid verifying specific implementation choices (e.g., which library function is called, internal state variables)
  - Tests should remain stable when internal implementation changes, as long as behavior remains the same
  - Example: Test that speech is detected correctly, not that `VADIterator` is called with specific parameters

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
- [ ] Tests verify behavior through public interfaces, not implementation details (see [CODING_STANDARDS.md](CODING_STANDARDS.md))
- [ ] Tests don't access private methods or internal attributes
- [ ] Tests remain stable when internal implementation changes
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

## Reducing Duplication in Test Cases

When multiple tests share the same setup, mocks, or patterns, extract shared helpers so tests stay short and changes stay in one place. This reduces repetition and keeps future test generation consistent.

### Module constant for patch targets

Define a single constant for the module under test and use it in all `patch()` targets. This avoids repeating long paths and makes renames easier.

```python
MODULE = "src.voice_assistant.audio.output.tts_engine_edge"

with patch(f"{MODULE}.shutil.which", return_value=None), \
     patch(f"{MODULE}.edge_tts") as mock_et:
    ...
```

### Shared helpers for mock construction

If several tests build the same kind of mock (e.g. a Communicate mock with a stream, a fake subprocess), extract a small function that returns the configured mock. Each test then calls the helper instead of inlining the same setup.

```python
def make_communicate_mock(mp3_chunks):
    """Mock edge_tts.Communicate whose stream yields type=audio chunks."""
    async def stream():
        for data in mp3_chunks:
            yield {"type": "audio", "data": data}
    mock = MagicMock()
    mock.stream = stream
    return mock
```

Use the same idea for other repeated mocks (e.g. `make_pydub_segment(...)`, `make_ffmpeg_mock_proc(...)`).

### Collecting async stream results

When tests only need to assert on the list of items produced by an async generator, use a small async helper instead of repeating the same loop in every test.

```python
async def collect_chunks(engine, text, **kwargs):
    """Run engine.generate_stream(text, **kwargs) and return list of AudioChunk."""
    chunks = []
    async for c in engine.generate_stream(text, **kwargs):
        chunks.append(c)
    return chunks

# In tests:
chunks = await collect_chunks(engine, "hello", language="en")
assert len(chunks) == 1
```

### Single-level patch blocks

Prefer one `with` block with multiple `patch()` calls over nested `with` blocks. This keeps the test body flat and makes it clear which patches apply together.

```python
with patch(f"{MODULE}.shutil.which", return_value=None), \
     patch(f"{MODULE}.edge_tts") as mock_et, \
     patch(f"{MODULE}.AudioSegment") as mock_as:
    mock_et.Communicate.return_value = communicate
    mock_as.from_file.return_value = segment
    engine = EdgeTTSEngine(config)
    chunks = await collect_chunks(engine, "hello", language="en")
assert len(chunks) == 1
mock_et.Communicate.assert_called_once_with("hello", "en-US-JennyNeural")
```

Put assertions that use mocks (e.g. `mock_et.Communicate.assert_called_once_with(...)`) after the `with` block if the mock is only needed for that assertion.

### Parameterized callbacks (e.g. interrupt-after-N)

When tests need a callable that changes behavior after N calls (e.g. `is_interrupted` that returns True after the first call), use a small factory instead of duplicating the same closure and counter in each test.

```python
def make_interrupt_after(threshold):
    """Return is_interrupted callable that returns True after (threshold + 1) calls."""
    call_count = [0]
    def is_interrupted():
        call_count[0] += 1
        return call_count[0] > threshold
    return is_interrupted

# In tests:
is_interrupted = make_interrupt_after(1)
chunks = await collect_chunks(engine, "hi", is_interrupted=is_interrupted)
```

### Summary

- **Module constant**: One `MODULE` (or similar) for all patch targets.
- **Mock helpers**: `make_*` functions for repeated mock shapes (Communicate, segment, subprocess, etc.).
- **Async collection**: One `collect_*` (or similar) helper for “run async generator, return list”.
- **Flat patches**: One `with patch(...), patch(...):` per test; assertions outside when they only need mocks.
- **Callback factories**: `make_interrupt_after(n)` or similar for “callable that flips after N calls”.

Reference: `tests/test_tts_engine_edge.py` for a full example of these patterns.

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
- [ ] **Duplication minimized** - shared helpers for mocks, patch targets (MODULE), async collection, and parameterized callbacks (see “Reducing Duplication in Test Cases”)

## Running Tests Before Commits

- Run full suite before major commits
- Ensure all tests pass locally before pushing
- Check test coverage for new code
- Verify test execution time is acceptable (< 30 seconds for full suite)
