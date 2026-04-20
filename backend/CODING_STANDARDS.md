# Backend Coding Standards

This document defines coding standards for the Tank Backend API Server.

## Code Style

### Python Style

- **PEP 8**: Follow PEP 8 style guide
- **Line Length**: 100 characters max
- **Imports**: Group by standard library, third-party, local
- **Type Hints**: Use type hints for all function signatures

### Async/Await

- **All I/O operations must be async**
- Use `async`/`await` for network, file, database operations
- Use `asyncio.create_task()` for concurrent operations
- Use thread pools (`asyncio.to_thread`) for CPU-intensive work

```python
# ✅ Good: Async I/O
async def fetch_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()

# ✅ Good: CPU work in thread pool
async def transcribe_audio(audio_data):
    return await asyncio.to_thread(whisper_model.transcribe, audio_data)

# ❌ Bad: Blocking I/O in async function
async def fetch_data():
    response = requests.get(url)  # Blocks event loop!
    return response.json()
```

### Type Hinting

- **Use `typing` module for all type annotations**
- Annotate function parameters and return types
- Use `Optional`, `List`, `Dict`, `Tuple` as needed
- Use `Protocol` for structural typing

```python
from typing import Optional, List, Dict, Any

async def process_message(
    message: str,
    language: Optional[str] = None,
    metadata: Dict[str, Any] = None
) -> List[str]:
    """Process a message and return responses."""
    ...
```

### Error Handling

- **Use specific exception types**
- Provide context in error messages
- Log errors with appropriate levels
- Graceful degradation for non-critical failures

```python
# ✅ Good: Specific exceptions with context
try:
    result = await llm.complete(prompt)
except httpx.TimeoutException as e:
    logger.error(f"LLM timeout after {timeout}s: {e}")
    raise LLMTimeoutError(f"Request timed out: {e}") from e
except httpx.HTTPStatusError as e:
    logger.error(f"LLM HTTP error {e.response.status_code}: {e}")
    raise LLMAPIError(f"API error: {e}") from e

# ❌ Bad: Bare except with no context
try:
    result = await llm.complete(prompt)
except:
    return "Error"
```

### Logging

- **Use `logging` module, not `print`**
- Use appropriate log levels: DEBUG, INFO, WARNING, ERROR
- Include context in log messages
- Use structured logging for production

```python
import logging

logger = logging.getLogger(__name__)

# ✅ Good: Structured logging with context
logger.info(f"Processing message from user {user_id}, language={language}")
logger.debug(f"LLM request: {prompt[:100]}...")
logger.error(f"Tool execution failed: {tool_name}", exc_info=True)

# ❌ Bad: Print statements
print("Processing message")
```

## Module Organization

### Imports

- **Within `src/tank_backend/`, use relative imports**
- Avoid circular imports
- Group imports: standard library, third-party, local

```python
# ✅ Good: Relative imports
from ..core.events import BrainInputEvent
from ..audio.input import AudioInput
from .settings import BackendConfig

# ❌ Bad: Absolute imports within package
from tank_backend.core.events import BrainInputEvent
```

### File Structure

- **One class per file** (except small dataclasses)
- Keep `__init__.py` lightweight (imports/exports only)
- Use descriptive file names matching class names

```
src/tank_backend/
├── api/
│   ├── __init__.py          # Exports only
│   ├── server.py            # Health, metrics endpoints
│   ├── router.py            # WebSocket handler
│   ├── approvals.py         # Approval REST API
│   └── metrics.py           # Metrics endpoint
├── agents/
│   ├── base.py              # Agent ABC, AgentState, AgentOutput
│   ├── graph.py             # AgentGraph orchestrator
│   ├── approval.py          # ApprovalManager + policy
│   ├── factory.py           # Agent factory
│   └── chat_agent.py        # Single conversational agent (all tools)
├── pipeline/
│   ├── processor.py         # Processor ABC, AudioCaps, FlowReturn
│   ├── event.py             # PipelineEvent
│   ├── queue.py             # ThreadedQueue
│   ├── fan_out_queue.py     # FanOutQueue
│   ├── bus.py               # Bus, BusMessage
│   ├── builder.py           # PipelineBuilder, Pipeline
│   ├── health.py            # HealthAggregator
│   ├── processors/          # Concrete processors
│   └── observers/           # Bus subscribers
├── llm/
│   └── llm.py               # LLM client
├── observability/
│   ├── langfuse_client.py   # Langfuse init
│   └── trace.py             # Trace ID generation
├── persistence/
│   └── checkpointer.py      # SQLite checkpointer
├── core/
│   ├── __init__.py
│   ├── brain.py             # Brain class (legacy)
│   ├── assistant.py         # Assistant class
│   └── events.py            # Event dataclasses
```

## FastAPI Patterns

### Route Handlers

- **Use dependency injection for shared resources**
- Validate input with Pydantic models
- Return appropriate HTTP status codes
- Handle errors with exception handlers

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    language: Optional[str] = None

@router.post("/chat")
async def chat(
    request: ChatRequest,
    brain: Brain = Depends(get_brain)
) -> Dict[str, Any]:
    """Process a chat message."""
    try:
        response = await brain.process_input(
            request.message,
            request.language
        )
        return {"response": response}
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

### WebSocket Handlers

- **Handle connection lifecycle properly**
- Validate messages before processing
- Send error messages to client
- Clean up resources on disconnect

```python
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # Validate and process
            await process_message(data)
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    finally:
        # Clean up resources
        await cleanup()
```

## Audio Processing Patterns

### Audio Data

- **Use numpy arrays for audio data**
- Use float32 for PCM audio
- Document sample rate and format
- Use consistent chunk sizes

```python
import numpy as np

def process_audio(
    audio: np.ndarray,  # float32, shape (n_samples,)
    sample_rate: int = 16000
) -> np.ndarray:
    """Process audio data."""
    assert audio.dtype == np.float32
    assert len(audio.shape) == 1
    ...
```

### Streaming Audio

- **Use async generators for streaming**
- Yield small chunks for low latency
- Handle interruption via cancellation

```python
async def generate_audio_stream(
    text: str,
    language: str
) -> AsyncIterator[bytes]:
    """Generate audio stream from text."""
    async for chunk in tts_engine.generate(text, language):
        if should_interrupt():
            break
        yield chunk
```

## Pipeline Processor Development

### Processor Pattern

- **Inherit from `Processor`** (or extend an existing processor like `ChatAgent`)
- Implement `async process()` as an async generator
- Use `FlowReturn` for backpressure signaling
- Declare `input_caps` / `output_caps` for audio processors
- Handle `PipelineEvent` for interrupt/flush support

```python
from ..pipeline.processor import Processor, FlowReturn, AudioCaps
from ..pipeline.event import PipelineEvent

class MyProcessor(Processor):
    """Processor description."""

    name = "my_processor"
    input_caps = AudioCaps(sample_rate=16000)   # None for non-audio input
    output_caps = None                           # None for non-audio output

    def __init__(self, bus, config=None):
        self.bus = bus
        self.config = config

    async def process(self, item):
        """Process input, yield (flow_return, output) pairs."""
        result = await self._transform(item)
        yield FlowReturn.OK, result

    def handle_event(self, event: PipelineEvent) -> bool:
        """Handle control event. Return True if consumed."""
        if event.type == "interrupt":
            self._cancel_current_work()
            return False  # propagate to next processor
        return False  # default: propagate

    async def start(self):
        """Called when pipeline starts."""
        pass

    async def stop(self):
        """Called when pipeline stops."""
        pass
```

### Bus Messaging

- **Post metrics and state changes to Bus** — never couple processors directly
- Use descriptive message types: `"metric"`, `"ui_update"`, `"qos"`, `"error"`
- Include `source` (processor name) and `timestamp` in every message

```python
from ..pipeline.bus import Bus, BusMessage
import time

# Posting a metric
self.bus.post(BusMessage(
    type="metric",
    source=self.name,
    payload={"stage": self.name, "duration_ms": elapsed_ms},
    timestamp=time.time(),
))
```

### Observer Pattern

- **Implement the observer protocol** — subscribe to Bus message types
- Keep observers lightweight — no blocking I/O in handlers

```python
class MyObserver:
    """Custom observer for pipeline metrics."""

    def __init__(self, bus: Bus):
        bus.subscribe("metric", self.on_message)

    def on_message(self, message: BusMessage):
        # Process metric — aggregate, log, alert, etc.
        pass
```

## Agent Development

### Agent Pattern

- A single `ChatAgent` handles all conversations — it manages LLM calling, tool execution, and streaming
- Configure via `system_prompt.txt` and `config.yaml` (no subclassing needed)
- Yield `AgentOutput` for each piece of streaming output
- Use `AgentOutputType` enum for structured output types

### Agent State

- **AgentState is shared** — agents read/write to a common state object
- Include `messages`, `metadata`, `agent_history`, and `turn` counter
- Do not store large data in state — use references (file paths, IDs)

### Approval Integration

- **Check approval policy before tool execution** — ChatAgent does this automatically
- Tools in `require_approval` list trigger `APPROVAL_NEEDED` output
- Tools in `require_approval_first_time` ask once per session, then auto-approve

## Tool Development

### Tool Pattern

**Prefer strong types over dicts:**

- **Inherit from `BaseTool`**
- Implement `get_info()` → `ToolInfo` and `execute()` → `ToolResult | str`
- Return `ToolResult` for structured results (recommended)
- Return `str` for plain text results (e.g. skill instructions)
- **Never return `dict`** — use `ToolResult` for type safety

```python
import json
from .base import BaseTool, ToolInfo, ToolParameter, ToolResult

class MyTool(BaseTool):
    """Tool description."""

    def get_info(self) -> ToolInfo:
        return ToolInfo(
            name="my_tool",
            description="What this tool does",
            parameters=[
                ToolParameter(
                    name="param1",
                    type="string",
                    description="Parameter description",
                    required=True,
                ),
            ],
        )

    async def execute(self, param1: str) -> ToolResult:
        """Execute the tool."""
        # Do work
        result_data = {"input": param1, "output": "processed"}

        # Return ToolResult with full data for LLM, summary for UI
        return ToolResult(
            content=json.dumps(result_data, ensure_ascii=False),
            display=f"Processed '{param1}' successfully",
        )
```

**Error handling:**

```python
    async def execute(self, param1: str) -> ToolResult:
        try:
            result = do_work(param1)
            return ToolResult(
                content=json.dumps({"result": result}, ensure_ascii=False),
                display=f"Success: {result}",
            )
        except Exception as e:
            return ToolResult(
                content=json.dumps({"error": str(e)}, ensure_ascii=False),
                display=f"Error: {e}",
                error=True,
            )
```

### Why ToolResult over dict?

**Type safety prevents bugs:**

```python
# BAD: Weak typing, easy to make mistakes
def process_data(data: dict) -> dict:
    return {"result": data["value"] * 2, "status": "ok"}

# GOOD: Strong typing, IDE support, validation
@dataclass(frozen=True)
class ProcessResult:
    result: int
    status: str

def process_data(data: InputData) -> ProcessResult:
    return ProcessResult(result=data.value * 2, status="ok")
```

**Benefits:**
- Type safety — catch errors at development time
- IDE autocomplete and refactoring support
- Self-documenting — the type tells you what fields exist
- Immutability (frozen=True) — prevents accidental mutation
- Prevents "magic key" bugs (no implicit behavior based on key names)

**When to use each:**
- `@dataclass(frozen=True)` — Simple data containers, return types
- `BaseModel` (Pydantic) — Input validation, API schemas, config
- `dict` — Only for truly dynamic data (JSON from external APIs)

### Tool Registration

Tools are organized into `ToolGroup` classes that share construction dependencies:

```python
class MyToolGroup(ToolGroup):
    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def create_tools(self) -> list[BaseTool]:
        if not self._config.get("enabled", True):
            return []
        return [MyTool(self._config)]
```

ToolManager instantiates all groups and collects their tools.

## Configuration

### Environment Variables

- **Use Pydantic for configuration**
- Provide sensible defaults
- Validate required fields
- Document all settings

```python
from pydantic_settings import BaseSettings


class BackendConfig(BaseSettings):
    """Backend configuration."""

    llm_api_key: str  # Required
    llm_model: str = "gpt-3.5-turbo"  # Default
    whisper_model_size: str = "base"

    class Config:
        env_file = "core/.env"
        env_file_encoding = "utf-8"
```

## Testing Patterns

See [TESTING.md](TESTING.md) for comprehensive testing guidelines.

### Key Principles

- **Test behavior, not implementation**
- Mock external dependencies (LLM, APIs)
- Use fixtures for common test data
- Test async code with pytest-asyncio

## Code Quality Checklist

Before committing code:

- [ ] All functions have type hints
- [ ] All I/O operations are async
- [ ] Errors are handled gracefully
- [ ] Logging is used instead of print
- [ ] Relative imports within package
- [ ] Tests are written and passing
- [ ] Code follows PEP 8 style
- [ ] Documentation is updated
- [ ] Processors use `FlowReturn` for backpressure
- [ ] Bus messages posted for observable events
- [ ] Approval policies checked for new tools
