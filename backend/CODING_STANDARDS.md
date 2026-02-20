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
│   ├── websocket.py         # WebSocketHandler class
│   └── routes.py            # FastAPI routes
├── core/
│   ├── __init__.py
│   ├── brain.py             # Brain class
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

## Tool Development

### Tool Pattern

- **Inherit from `BaseTool`**
- Implement `get_parameters()` and `execute()`
- Use type hints for parameters
- Return string results

```python
from .base import BaseTool

class MyTool(BaseTool):
    """Tool description."""

    name = "my_tool"
    description = "What this tool does"

    def get_parameters(self) -> dict:
        """Return parameter schema."""
        return {
            "param1": {
                "type": "string",
                "description": "Parameter description"
            }
        }

    def execute(self, param1: str) -> str:
        """Execute the tool."""
        # Implementation
        return result
```

### Tool Registration

- **Tools are auto-registered by ToolManager**
- Use conditional registration for optional tools
- Validate required configuration

```python
# In ToolManager.__init__
if config.serper_api_key:
    self.register_tool(WebSearchTool(config))
```

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
        env_file = ".env"
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
