# Coding Standards

This document defines coding standards, design principles, and code quality guidelines for the Tank Voice Assistant project.

## Code Simplification Principles

### Remove Unnecessary Abstraction Layers

- **Avoid wrapping functionality that already provides what you need**
  - If a library/component already handles threshold comparison, don't add another layer
  - If a component returns the exact result you need, use it directly instead of converting
  - Avoid creating wrapper methods that only convert formats without adding logic
  - Example: If `VADIterator` already does threshold comparison and returns boolean-like results, don't wrap it with a method that converts to float and back to boolean

### Eliminate Redundant Logic

- **Don't duplicate functionality that's already handled**
  - If a dependency already performs a check/comparison, don't repeat it
  - Pass configuration parameters directly to dependencies that support them
  - Example: Pass `speech_threshold` directly to `VADIterator` instead of doing threshold comparison yourself

### Direct Usage Over Wrappers

- **Prefer direct usage when the abstraction adds no value**
  - If an intermediate method only converts formats without adding logic, consider removing it
  - Keep code paths simple and direct
  - Example: Call `VADIterator` directly in `_process_chunk` instead of through `_infer_speech_prob` that only converts return values

## Code Style & Patterns

### Async/Await

- **The core system is asynchronous. Ensure strictly non-blocking code in the main thread**
  - Use `async`/`await` for all I/O operations
  - Avoid blocking operations in async functions
  - Use thread pools for CPU-intensive or blocking operations

### Type Hinting

- **Use `typing` extensively for type annotations**
  - Use `List`, `Optional`, `Dict`, `Tuple` from `typing` module
  - Annotate function parameters and return types
  - Use type hints for better IDE support and code clarity

### Error Handling

- **Implement graceful degradation**
  - If a component fails (e.g., TTS fails), log it but don't crash the entire system
  - Use `try/except` blocks around external service calls
  - Provide user-friendly error messages in multiple languages
  - Comprehensive logging throughout the system

### Logging

- **Use `logging` module, not `print`**
  - Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
  - Log important events and errors
  - Exception: Use `print` only for CLI user feedback

### Imports (Critical)

- **Within `src/voice_assistant/`, always use relative imports**
  - Use relative imports to avoid package-resolution issues across different runners/environments
  - **Do**:
    - `from ...core.shutdown import StopSignal`
    - `from ..audio.input import AudioInput`
    - `from ..audio.output import AudioOutput`
  - **Do not**:
    - `from voice_assistant.core.shutdown import StopSignal`
    - `import voice_assistant.audio.input`

### Module Layout

- **Keep `__init__.py` lightweight**
  - `__init__.py` should contain **imports/exports only**
  - Do not define real classes/functions in `__init__.py`

- **One file, one class (except dataclasses)**
  - Prefer **one class per file** to keep modules focused
  - Exception: small `@dataclass` types may share a file when they are tightly related

## Technical Patterns

### Core Design Philosophy

- **Emphasize responsiveness and interruption**
  - The assistant listens continuously and can be interrupted by the user at any time
  - Interruption can occur during LLM processing or TTS playback
  - All long-running tasks must be cancellable

### Tool System

- **Tools use declarative parameter schemas with type validation**
  - ToolManager automatically converts tools to OpenAI function calling format
  - LLM handles iterative tool calling until completion
  - Tool results are properly formatted as tool messages in conversation history

### Continuous Listening System

- **Always-on voice activity detection with configurable energy thresholds**
  - Automatic speech segmentation: starts recording on speech, stops after 2 seconds of silence
  - Real-time interruption: any detected speech immediately cancels current LLM/TTS tasks
  - Non-blocking audio processing with 100ms chunk granularity
  - Thread-pool transcription to avoid blocking the event loop

### Task Interruption Pattern

- **All long-running tasks (LLM completion, TTS generation/playback) are cancellable**
  - Speech detection triggers immediate interruption of current operations
  - Graceful task cleanup with proper resource management
  - Conversation state preservation across interruptions
  - All async tasks are designed to be cancellable for responsive interaction

### Language Handling

- **Automatic language detection from speech input**
  - Context-aware TTS voice selection (Chinese vs English)
  - System prompt supports bilingual responses
  - Both Chinese and English are first-class supported languages

## Code Modification Guidelines

### Modifying Core Components

- **When modifying `assistant.py`, be extremely careful with interruption logic**
  - The `_handle_speech_interruption` method is critical for system responsiveness
  - Test interruption scenarios thoroughly after any changes

### Adding Tools

- **When adding tools, follow the standard pattern**
  - Inherit from `BaseTool` (`src/voice_assistant/tools/base.py`)
  - Register the tool in `ToolManager`
  - Follow the TDD workflow: define interface → implement → add tests → register