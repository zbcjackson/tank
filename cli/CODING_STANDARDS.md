# CLI Coding Standards

This document defines coding standards for the Tank CLI/TUI Client.

## Code Style

### Python Style

- **PEP 8**: Follow PEP 8 style guide
- **Line Length**: 100 characters max
- **Imports**: Group by standard library, third-party, local
- **Type Hints**: Use type hints for all function signatures

### Async/Await

- **All I/O operations must be async**
- Use `async`/`await` for network, audio, file operations
- Use `asyncio.create_task()` for concurrent operations
- Textual components use async methods

```python
# ✅ Good: Async I/O
async def send_message(self, message: str):
    async with websockets.connect(self.server_url) as ws:
        await ws.send(json.dumps({"type": "text", "content": message}))

# ❌ Bad: Blocking I/O in async function
async def send_message(self, message: str):
    ws = websockets.connect(self.server_url)  # Blocks!
    ws.send(message)
```

### Type Hinting

- **Use `typing` module for all type annotations**
- Annotate function parameters and return types
- Use `Optional`, `List`, `Dict`, `Tuple` as needed

```python
from typing import Optional, List, Dict, Any

async def process_audio(
    audio_data: bytes,
    sample_rate: int = 16000,
    metadata: Optional[Dict[str, Any]] = None
) -> List[bytes]:
    """Process audio data."""
    ...
```

### Error Handling

- **Use specific exception types**
- Provide context in error messages
- Log errors with appropriate levels
- Show user-friendly messages in UI

```python
# ✅ Good: Specific exceptions with user feedback
try:
    await self.connect_to_server()
except ConnectionRefusedError:
    self.notify("Cannot connect to server. Is it running?", severity="error")
    logger.error(f"Connection refused: {self.server_url}")
except TimeoutError:
    self.notify("Connection timeout. Check your network.", severity="warning")
    logger.warning(f"Connection timeout: {self.server_url}")

# ❌ Bad: Bare except with no feedback
try:
    await self.connect_to_server()
except:
    pass
```

### Logging

- **Use `logging` module, not `print`**
- Use appropriate log levels: DEBUG, INFO, WARNING, ERROR
- Include context in log messages

```python
import logging

logger = logging.getLogger(__name__)

# ✅ Good: Structured logging
logger.info(f"Connected to server: {server_url}")
logger.debug(f"Received message: {message[:100]}...")
logger.error(f"WebSocket error: {error}", exc_info=True)

# ❌ Bad: Print statements
print("Connected to server")
```

## Module Organization

### Imports

- **Within `src/tank_cli/`, use relative imports**
- Avoid circular imports
- Group imports: standard library, third-party, local

```python
# ✅ Good: Relative imports
from ..config.settings import CLIConfig
from ..audio.input import AudioInput
from .ui.header import Header

# ❌ Bad: Absolute imports within package
from tank_cli.config.settings import CLIConfig
```

### File Structure

- **One class per file** (except small dataclasses)
- Keep `__init__.py` lightweight (imports/exports only)
- Use descriptive file names matching class names

```
src/tank_cli/
├── tui/
│   ├── __init__.py          # Exports only
│   ├── app.py               # TankApp class
│   └── ui/
│       ├── header.py        # Header widget
│       ├── conversation.py  # Conversation widget
│       └── footer.py        # Footer widget
```

## Textual Patterns

### Widget Development

- **Inherit from appropriate Textual widgets**
- Use reactive attributes for state management
- Implement compose() for child widgets
- Use CSS for styling

```python
from textual.app import ComposeResult
from textual.widgets import Static
from textual.reactive import reactive

class StatusWidget(Static):
    """Display connection status."""

    status: reactive[str] = reactive("disconnected")

    def compose(self) -> ComposeResult:
        yield Static(id="status-text")

    def watch_status(self, new_status: str) -> None:
        """React to status changes."""
        self.query_one("#status-text").update(new_status)
```

### Message Handling

- **Use Textual's message system for component communication**
- Define custom messages for domain events
- Handle messages in on_<message_name> methods

```python
from textual.message import Message

class AudioReceived(Message):
    """Audio data received from server."""

    def __init__(self, audio_data: bytes) -> None:
        self.audio_data = audio_data
        super().__init__()

class ConversationWidget(Widget):
    def on_audio_received(self, message: AudioReceived) -> None:
        """Handle audio received message."""
        await self.play_audio(message.audio_data)
```

### Async Actions

- **Use async methods for I/O operations**
- Use `call_from_thread()` for thread-safe UI updates
- Use `run_worker()` for background tasks

```python
from textual.worker import Worker

class TankApp(App):
    async def action_send_message(self) -> None:
        """Send message to server."""
        message = self.query_one("#input").value
        await self.client.send(message)

    def start_audio_capture(self) -> None:
        """Start audio capture in background."""
        self.run_worker(self._capture_audio(), exclusive=True)

    async def _capture_audio(self) -> None:
        """Background audio capture worker."""
        async for chunk in self.audio_input:
            await self.client.send_audio(chunk)
```

## WebSocket Patterns

### Connection Management

- **Handle connection lifecycle properly**
- Implement reconnection logic
- Clean up resources on disconnect

```python
class WebSocketClient:
    async def connect(self) -> None:
        """Connect to server with retry logic."""
        retry_count = 0
        while retry_count < self.max_retries:
            try:
                self.ws = await websockets.connect(self.url)
                logger.info(f"Connected to {self.url}")
                return
            except Exception as e:
                retry_count += 1
                logger.warning(f"Connection failed (attempt {retry_count}): {e}")
                await asyncio.sleep(self.retry_delay)
        raise ConnectionError("Max retries exceeded")

    async def disconnect(self) -> None:
        """Disconnect from server."""
        if self.ws:
            await self.ws.close()
            self.ws = None
```

### Message Protocol

- **Use JSON for message serialization**
- Validate message structure
- Handle unknown message types gracefully

```python
async def handle_message(self, raw_message: str) -> None:
    """Handle incoming WebSocket message."""
    try:
        message = json.loads(raw_message)
        msg_type = message.get("type")

        if msg_type == "audio":
            await self.handle_audio(message["data"])
        elif msg_type == "text":
            await self.handle_text(message["content"])
        elif msg_type == "status":
            await self.handle_status(message["status"])
        else:
            logger.warning(f"Unknown message type: {msg_type}")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
    except KeyError as e:
        logger.error(f"Missing required field: {e}")
```

## Audio Processing Patterns

### Audio Capture

- **Use sounddevice for audio input**
- Process audio in chunks
- Handle device errors gracefully

```python
import sounddevice as sd
import numpy as np

async def capture_audio(
    sample_rate: int = 16000,
    chunk_size: int = 1600
) -> AsyncIterator[np.ndarray]:
    """Capture audio from microphone."""
    queue = asyncio.Queue()

    def callback(indata, frames, time, status):
        if status:
            logger.warning(f"Audio input status: {status}")
        queue.put_nowait(indata.copy())

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype=np.float32,
        blocksize=chunk_size,
        callback=callback
    ):
        while True:
            chunk = await queue.get()
            yield chunk
```

### Audio Playback

- **Use sounddevice for audio output**
- Handle playback interruption
- Manage audio buffer

```python
async def play_audio(audio_data: bytes) -> None:
    """Play audio data through speaker."""
    try:
        # Decode audio data
        audio_array = np.frombuffer(audio_data, dtype=np.float32)

        # Play audio
        sd.play(audio_array, samplerate=16000)
        sd.wait()
    except Exception as e:
        logger.error(f"Audio playback error: {e}")
```

## Configuration

### Environment Variables

- **Use Pydantic for configuration**
- Provide sensible defaults
- Validate required fields

```python
from pydantic_settings import BaseSettings

class CLIConfig(BaseSettings):
    """CLI configuration."""

    server_host: str = "localhost"
    server_port: int = 8000
    sample_rate: int = 16000
    chunk_size: int = 1600

    @property
    def server_url(self) -> str:
        return f"ws://{self.server_host}:{self.server_port}/ws"

    class Config:
        env_prefix = "TANK_"
        env_file = ".env"
```

## Testing Patterns

See [TESTING.md](TESTING.md) for comprehensive testing guidelines.

### Key Principles

- **Test behavior, not implementation**
- Mock WebSocket connections
- Mock audio devices
- Use Textual's testing utilities

```python
from textual.pilot import Pilot

async def test_app_startup():
    """Test app starts successfully."""
    app = TankApp()
    async with app.run_test() as pilot:
        assert app.is_running
        assert pilot.app.title == "Tank Voice Assistant"
```

## Code Quality Checklist

Before committing code:

- [ ] All functions have type hints
- [ ] All I/O operations are async
- [ ] Errors are handled gracefully
- [ ] Logging is used instead of print
- [ ] Relative imports within package
- [ ] Tests are written and passing
- [ ] Code follows PEP 8 style
- [ ] UI is responsive and accessible
- [ ] WebSocket reconnection works
- [ ] Audio devices are properly released
